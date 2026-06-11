from flask import Flask, render_template, request, jsonify, redirect, url_for
import cv2
import numpy as np
import base64
from deepface import DeepFace
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from collections import Counter
from datetime import datetime
import random
import string
import os

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/analise_ia'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'uma_chave_muito_secreta_e_complexa'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# =============================================================
# MODELOS DO BANCO
# =============================================================

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id     = db.Column(db.Integer, primary_key=True)
    nome   = db.Column(db.String(100), nullable=False)
    email  = db.Column(db.String(100), unique=True, nullable=False)
    senha  = db.Column(db.String(255), nullable=False)
    tipo   = db.Column(db.String(20), default='Idoso')       # 'Idoso' ou 'Responsavel'
    codigo = db.Column(db.String(10), unique=True, nullable=True)  # Ex: AG-123456 (só idosos)


class RegistroEmocao(db.Model):
    __tablename__ = 'registros_emocao'
    id         = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    emocao     = db.Column(db.String(50), nullable=False)
    confianca  = db.Column(db.Float, nullable=False)
    data_hora  = db.Column(db.DateTime, default=db.func.now())
    usuario    = db.relationship('Usuario', backref='registros')


class Vinculo(db.Model):
    __tablename__ = 'vinculos'
    id               = db.Column(db.Integer, primary_key=True)
    responsavel_id   = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    idoso_id         = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    criado_em        = db.Column(db.DateTime, default=datetime.now)
    __table_args__   = (db.UniqueConstraint('responsavel_id', 'idoso_id'),)


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


# =============================================================
# HELPERS
# =============================================================

def gerar_codigo():
    """Gera um código único no formato AG-XXXXXX para idosos."""
    while True:
        sufixo = ''.join(random.choices(string.digits, k=6))
        codigo = f'AG-{sufixo}'
        if not Usuario.query.filter_by(codigo=codigo).first():
            return codigo


def emocao_emoji(emocao):
    mapa = {'Feliz': '😊', 'Triste': '🥺', 'Bravo': '😤', 'Neutro': '🙂',
            'Surpreso': '😮', 'Medo': '😨', 'Nojo': '😒'}
    return mapa.get(emocao, '👀')

app.jinja_env.globals['emocao_emoji'] = emocao_emoji


# =============================================================
# FUNÇÕES DE ANÁLISE DE IMAGEM (sem alterações)
# =============================================================

def preprocessar_imagem(img):
    if img is None:
        return None
    height, width = img.shape[:2]
    if width > 640 or height > 640:
        scale = 640 / max(width, height)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def tentar_analisar(img):
    detectors = ['mtcnn', 'retinaface', 'mediapipe', 'ssd', 'yunet']
    for detector in detectors:
        try:
            res = DeepFace.analyze(
                img, actions=['emotion'],
                enforce_detection=False,
                detector_backend=detector,
                align=True, silent=True, anti_spoofing=False
            )
            if isinstance(res, list):
                res = res[0]
            emocao = res['dominant_emotion']
            confianca = res['emotion'][emocao]
            print(f"✅ Detector {detector} → {emocao} ({confianca:.1f}%)")
            if confianca >= 30:
                return emocao, confianca
        except Exception as e:
            print(f"❌ Detector {detector} falhou: {str(e)[:100]}")
            continue
    print("⚠️ Nenhum detector conseguiu identificar o rosto")
    return None, 0


# =============================================================
# ROTAS DE NAVEGAÇÃO
# =============================================================

@app.route('/')
def index():
    return render_template('menup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    tipo = request.args.get('tipo', 'Idoso')

    if request.method == 'POST':
        if request.is_json:
            dados = request.get_json()
            email = dados.get('email')
            senha = dados.get('senha')
        else:
            email = request.form.get('email')
            senha = request.form.get('senha')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and check_password_hash(usuario.senha, senha):
            login_user(usuario)
            # Redireciona para o dashboard correto conforme o tipo
            destino = 'dashboard_responsavel' if usuario.tipo == 'Responsavel' else 'dashboard'
            return jsonify({'success': True, 'message': 'Bem-vindo!',
                            'nome': usuario.nome, 'redirect': url_for(destino)}), 200

        return jsonify({'success': False, 'message': 'E-mail ou senha incorretos'}), 401

    return render_template('login.html', tipo=tipo)


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        dados = request.get_json() if request.is_json else request.form
        senha_hash = generate_password_hash(dados['senha'])
        tipo = dados.get('tipo', 'Idoso')

        novo_usuario = Usuario(
            nome=dados['nome'],
            email=dados['email'],
            senha=senha_hash,
            tipo=tipo,
            codigo=gerar_codigo() if tipo == 'Idoso' else None
        )

        try:
            db.session.add(novo_usuario)
            db.session.commit()
            return jsonify({'success': True, 'codigo': novo_usuario.codigo}), 201
        except Exception:
            db.session.rollback()
            return jsonify({'erro': 'E-mail já cadastrado'}), 400

    return render_template('cadastro.html')


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.tipo == 'Responsavel':
        return redirect(url_for('dashboard_responsavel'))
    return render_template('dashboard.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


# =============================================================
# ROTA DE INTELIGÊNCIA ARTIFICIAL (sem alterações)
# =============================================================

@app.route('/analisar_expressao', methods=['POST'])
@login_required
def analisar():
    try:
        print("🔍 Requisição recebida - Iniciando análise...")
        data = request.json.get('image')
        if not data:
            return jsonify({'emocao': 'Rosto não detectado', 'confianca': 0,
                            'mensagem': 'Imagem não recebida'})

        encoded_data = data.split(',')[1]
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None or img.size == 0:
            return jsonify({'emocao': 'Rosto não detectado', 'confianca': 0,
                            'mensagem': 'Imagem inválida'})

        print(f"✅ Imagem decodificada - Shape: {img.shape}")
        img = preprocessar_imagem(img)

        emocoes_detectadas = []
        confiancas = []
        for i in range(3):
            print(f"Tentativa {i+1}/3")
            resultado = tentar_analisar(img)
            if resultado and resultado[0]:
                emocao, confianca = resultado
                emocoes_detectadas.append(emocao)
                confiancas.append(confianca)

        if not emocoes_detectadas:
            return jsonify({'emocao': 'Rosto não detectado', 'confianca': 0,
                            'mensagem': 'Não foi possível detectar seu rosto.'})

        emocao_final = Counter(emocoes_detectadas).most_common(1)[0][0]
        confianca_media = round(sum(confiancas) / len(confiancas), 2)

        traducoes = {
            'happy': 'Feliz', 'sad': 'Triste', 'angry': 'Bravo',
            'neutral': 'Neutro', 'surprise': 'Surpreso',
            'fear': 'Medo', 'disgust': 'Nojo'
        }
        emocao_pt = traducoes.get(emocao_final, emocao_final)

        novo_registro = RegistroEmocao(
            usuario_id=current_user.id,
            emocao=emocao_pt,
            confianca=confianca_media
        )
        db.session.add(novo_registro)
        db.session.commit()

        print(f"🎉 Análise finalizada: {emocao_pt} ({confianca_media}%)")
        return jsonify({'emocao': emocao_pt, 'confianca': confianca_media, 'mensagem': 'Sucesso'})

    except Exception as e:
        print("❌ Erro geral na análise:", str(e))
        import traceback
        traceback.print_exc()
        return jsonify({'emocao': 'Rosto não detectado', 'confianca': 0,
                        'mensagem': 'Erro interno no servidor'})


# =============================================================
# ROTA DE HISTÓRICO DO IDOSO (sem alterações)
# =============================================================

@app.route('/historico')
@login_required
def historico():
    registros = RegistroEmocao.query.filter_by(
        usuario_id=current_user.id
    ).order_by(RegistroEmocao.data_hora.desc()).all()

    resultado = [
        {'emocao': r.emocao, 'confianca': r.confianca,
         'data_hora': r.data_hora.strftime('%d/%m/%Y %H:%M:%S')}
        for r in registros
    ]
    return jsonify(resultado)


# =============================================================
# DASHBOARD DO RESPONSÁVEL
# =============================================================

@app.route('/dashboard/responsavel')
@login_required
def dashboard_responsavel():
    if current_user.tipo != 'Responsavel':
        return redirect(url_for('dashboard'))

    vinculos = Vinculo.query.filter_by(responsavel_id=current_user.id).all()
    idosos_ids = [v.idoso_id for v in vinculos]
    idosos_raw = Usuario.query.filter(Usuario.id.in_(idosos_ids)).all() if idosos_ids else []

    idosos = []
    alertas = []

    for idoso in idosos_raw:
        registros = (
            RegistroEmocao.query
            .filter_by(usuario_id=idoso.id)
            .order_by(RegistroEmocao.data_hora.asc())
            .all()
        )

        historico_serializado = [
            {'emocao': r.emocao, 'confianca': r.confianca,
             'hora': r.data_hora.strftime('%d/%m %H:%M')}
            for r in registros
        ]

        ultima         = historico_serializado[-1] if historico_serializado else None
        ultima_emocao  = ultima['emocao'] if ultima else None
        ultima_analise = ultima['hora']   if ultima else None

        hoje = datetime.now().date()
        analises_hoje = sum(
            1 for r in registros
            if r.data_hora.date() == hoje
        )

        emocao_frequente = None
        if historico_serializado:
            contagem = Counter(r['emocao'] for r in historico_serializado)
            emocao_frequente = contagem.most_common(1)[0][0]

        idosos.append({
            'id':               idoso.id,
            'nome':             idoso.nome,
            'codigo':           idoso.codigo,
            'ultima_emocao':    ultima_emocao,
            'ultima_analise':   ultima_analise,
            'analises_hoje':    analises_hoje,
            'emocao_frequente': emocao_frequente,
            'historico':        historico_serializado,
        })

        if ultima_emocao in ('Triste', 'Bravo'):
            alertas.append({
                'nome':     idoso.nome,
                'nivel':    'alto' if ultima_emocao == 'Bravo' else 'medio',
                'mensagem': f'Última emoção registrada: {ultima_emocao}',
                'hora':     ultima_analise,
            })

    return render_template(
        'dashboard_responsavel.html',
        nome_responsavel=current_user.nome,
        idosos=idosos,
        alertas=alertas,
    )


# =============================================================
# HISTÓRICO COMPLETO DE UM IDOSO
# =============================================================

@app.route('/historico/<int:idoso_id>')
@login_required
def historico_idoso(idoso_id):
    if current_user.tipo != 'Responsavel':
        return redirect(url_for('dashboard'))

    Vinculo.query.filter_by(
        responsavel_id=current_user.id,
        idoso_id=idoso_id
    ).first_or_404()

    idoso = Usuario.query.get_or_404(idoso_id)

    registros = (
        RegistroEmocao.query
        .filter_by(usuario_id=idoso_id)
        .order_by(RegistroEmocao.data_hora.asc())
        .all()
    )

    historico = [
        {'emocao': r.emocao, 'confianca': r.confianca,
         'mensagem': f'Confiança: {r.confianca:.0f}%',
         'hora': r.data_hora.strftime('%d/%m/%Y às %H:%M')}
        for r in registros
    ]

    contagem = Counter(r['emocao'] for r in historico)

    return render_template(
        'historico_idoso.html',
        idoso=idoso,
        historico=historico,
        contagem=contagem,
    )


# =============================================================
# VINCULAR IDOSO (página)
# =============================================================

@app.route('/responsavel/vincular-idoso')
@login_required
def vincular_idoso():
    if current_user.tipo != 'Responsavel':
        return redirect(url_for('dashboard'))
    return render_template('vincular_idoso.html')


# =============================================================
# API: BUSCAR IDOSO POR CÓDIGO
# =============================================================

@app.route('/responsavel/buscar_idoso', methods=['POST'])
@login_required
def buscar_idoso():
    dados  = request.get_json()
    codigo = (dados.get('codigo') or '').strip().upper()

    if not codigo:
        return jsonify({'success': False, 'erro': 'Código não informado.'}), 400

    idoso = Usuario.query.filter_by(codigo=codigo, tipo='Idoso').first()
    if not idoso:
        return jsonify({'success': False, 'erro': 'Nenhum idoso encontrado com esse código.'}), 404

    ja_vinculado = Vinculo.query.filter_by(
        responsavel_id=current_user.id, idoso_id=idoso.id
    ).first()
    if ja_vinculado:
        return jsonify({'success': False, 'erro': 'Você já está vinculado a este idoso.'}), 409

    return jsonify({'success': True, 'idoso': {'id': idoso.id, 'nome': idoso.nome, 'email': idoso.email}})


# =============================================================
# API: CONFIRMAR VÍNCULO
# =============================================================

@app.route('/responsavel/vincular', methods=['POST'])
@login_required
def confirmar_vinculo():
    dados    = request.get_json()
    idoso_id = dados.get('idoso_id')

    if not idoso_id:
        return jsonify({'success': False, 'erro': 'ID do idoso não informado.'}), 400

    idoso = Usuario.query.filter_by(id=idoso_id, tipo='Idoso').first()
    if not idoso:
        return jsonify({'success': False, 'erro': 'Idoso não encontrado.'}), 404

    if Vinculo.query.filter_by(responsavel_id=current_user.id, idoso_id=idoso_id).first():
        return jsonify({'success': False, 'erro': 'Vínculo já existe.'}), 409

    db.session.add(Vinculo(responsavel_id=current_user.id, idoso_id=idoso_id))
    db.session.commit()
    return jsonify({'success': True})


# =============================================================
# API: DESVINCULAR IDOSO
# =============================================================

@app.route('/responsavel/desvincular', methods=['POST'])
@login_required
def desvincular_idoso():
    dados    = request.get_json()
    idoso_id = dados.get('idoso_id')

    vinculo = Vinculo.query.filter_by(
        responsavel_id=current_user.id, idoso_id=idoso_id
    ).first()

    if not vinculo:
        return jsonify({'success': False, 'erro': 'Vínculo não encontrado.'}), 404

    db.session.delete(vinculo)
    db.session.commit()
    return jsonify({'success': True})


# =============================================================
# INICIALIZAÇÃO
# =============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)

from flask import Flask, render_template, request, jsonify, redirect, url_for
import cv2
import numpy as np
import base64
from deepface import DeepFace
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/analise_ia'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'uma_chave_bem_segura'

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Esse modelo deve refletir as colunas da sua tabela 'usuarios'
class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios' # Nome exato da tabela na sua imagem
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_input = request.form.get('nome')
        pass_input = request.form.get('senha')

        # Busca o usuário pelo nome no banco
        usuario = Usuario.query.filter_by(nome=user_input).first()

        # Verifica se o usuário existe e se a senha bate
        if usuario and usuario.senha == pass_input:
            login_user(usuario)
            return redirect(url_for('dashboard'))
        
        return "Usuário ou senha incorretos", 401
        
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    # Segunda parada: Painel com a Webcam via Browser
    return render_template('dashboard.html')

@app.route('/analisar_expressao', methods=['POST'])
def analisar():
    try:
        # Pega a imagem que o JS mandou
        data = request.json['image']
        encoded_data = data.split(',')[1]
        
        # Converte de Base64 (texto) para imagem real
        nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # A DeepFace analisa o frame enviado
        res = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
        emo = res[0]['dominant_emotion']
        
        # Devolve a resposta pro JS
        return jsonify({'emocao': emo})
    except Exception as e:
        return jsonify({'emocao': f"Erro: {str(e)}"})

if __name__ == '__main__':
    # Roda o servidor
    app.run(debug=True)
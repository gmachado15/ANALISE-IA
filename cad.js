document.addEventListener('DOMContentLoaded', () => {

    const btnCadastrar = document.getElementById('btn-cadastrar');

    // PEGA O TIPO DA URL
    const params = new URLSearchParams(window.location.search);
    const tipo = params.get('tipo') || 'Idoso';

    btnCadastrar.addEventListener('click', async (e) => {

        e.preventDefault();

        const nome = document.getElementById('nome').value.trim();
        const email = document.getElementById('email').value.trim();
        const senha = document.getElementById('senha').value.trim();
        const confirmar = document.getElementById('confirmar_senha').value.trim();

        if (!nome || !email || !senha) {
            alert("Todos os campos são obrigatórios!");
            return;
        }

        if (senha !== confirmar) {
            alert("As senhas não coincidem!");
            return;
        }

        try {

            const response = await fetch('/cadastro', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },

                // ENVIA O TIPO
                body: JSON.stringify({
                    nome,
                    email,
                    senha,
                    tipo
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {

                alert("Cadastro realizado com sucesso!");

                // MANTÉM O TIPO AO VOLTAR PRO LOGIN
                window.location.href = `/login?tipo=${tipo}`;

            } else {
                alert(data.erro || "Erro ao cadastrar.");
            }

        } catch (error) {
            console.error("Erro:", error);
            alert("Erro ao conectar com o servidor Flask.");
        }
    });
});
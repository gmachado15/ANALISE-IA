document.addEventListener('DOMContentLoaded', () => {
    const btnEntrar = document.getElementById('btn-entrar');

    
    const params = new URLSearchParams(window.location.search);
    const tipo = params.get('tipo') || 'Idoso';

    btnEntrar.addEventListener('click', async (e) => {
        e.preventDefault();

        const email = document.getElementById('email').value.trim();
        const senha = document.getElementById('senha').value.trim();

        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },

                // ENVIA O TIPO
                body: JSON.stringify({
                    email,
                    senha,
                    tipo
                })
            });

            const data = await response.json();

            if (data.success) {

                // REDIRECIONA CONFORME O TIPO
                if (data.tipo === 'Responsavel') {
                    window.location.href = "/dashboard/responsavel";
                } else {
                    window.location.href = "/dashboard";
                }

            } else {
                alert(data.message || "E-mail ou senha incorretos.");
            }

        } catch (error) {
            alert("Erro de conexão com o servidor.");
        }
    });
});
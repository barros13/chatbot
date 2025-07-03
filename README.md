# Busca Inteligente

![Screenshot do Chatbot](https://i.imgur.com/xZniCjl.png)
(https://i.imgur.com/nB6BLau.png)

## ❯ Sobre o Projeto

O Busca Inteligente é um assistente de chat conversacional avançado, desenvolvido para uso principalmente em prefeituras. O objetivo é permitir que cidadãos e servidores encontrem informações complexas dentro de um vasto acervo de documentos públicos (leis, decretos, licitações, notícias, etc.) de forma rápida e intuitiva, usando linguagem natural.

O sistema vai além de uma simples busca por palavras-chave, utilizando a API do Google Gemini para entender a intenção do usuário, filtrar informações de múltiplas fontes de dados e gerar respostas coesas e precisas, citando os documentos utilizados.

---

## Funcionalidades Principais

* Análise de Intenção com IA: O sistema utiliza um modelo de linguagem (LLM) para interpretar a pergunta do usuário, corrigir erros de digitação e identificar o assunto principal da busca.
* Busca Híbrida e Priorizada: Combina uma busca literal (`LIKE`) para encontrar termos exatos com uma busca por relevância (`FULLTEXT`) para contexto, garantindo que os resultados mais específicos sejam sempre priorizados.
* Inferência Cruzada de Banco de Dados: O backend é capaz de buscar metadados (como títulos de publicações) em um banco de dados principal e usar essa informação para extrair o conteúdo textual completo de arquivos PDF armazenados em um segundo banco de dados.
* Filtragem e Geração de Resposta com IA: Uma segunda chamada à IA analisa os documentos encontrados, filtra apenas os mais relevantes para a pergunta e sintetiza uma resposta final em linguagem natural.
* Interface de Chat Moderna: Um frontend limpo, responsivo e com identidade visual, que funciona de forma isolada para não conflitar com os estilos do site principal.
* Controle de Custos: A aplicação foi otimizada para reduzir o consumo de tokens da API, e o guia de implantação inclui a configuração de alertas de orçamento e suspensão automática de faturamento no Google Cloud.

---

## Tecnologias Utilizadas

O projeto é dividido em um frontend integrado ao site e um backend independente.

* Frontend:
    * PHP: Para integração com o site existente.
    * HTML5, CSS3, JavaScript (Vanilla JS): Para a estrutura, estilo e lógica do chat.
    * Font Awesome: Para os ícones da interface.

* Backend:
    * Python 3.9+
    * Flask: Micro-framework web para criar a API.
    * Waitress: Servidor WSGI de produção, compatível com Windows.

* Inteligência Artificial:
    * Google Gemini API (gemini-2.5-flash): Para análise de intenção e geração de respostas.

* Banco de Dados:
    * MySQL: Dois bancos de dados separados:
        1.  `main_db`: Banco de dados principal do site (notícias, licitações, etc.).
        2.  `pdf_content_db`: Banco de dados com o conteúdo textual extraído e indexado dos arquivos PDF.

---

## Arquitetura

O fluxo de uma pergunta do usuário segue a seguinte arquitetura:

```
[Usuário] -> [Site PHP (Apache/Nginx)] -> [proxy.php] -> [Backend Python (Waitress)] -> [API Gemini / Bancos MySQL]
```

1.  O Frontend (no site PHP) envia a pergunta para o `proxy.php`.
2.  O Proxy PHP repassa a pergunta de forma segura para o Backend Python.
3.  O Backend Python:
    * Chama a API Gemini para analisar a intenção da pergunta.
    * Realiza buscas priorizadas nos dois bancos MySQL.
    * Faz a inferência cruzada entre os bancos.
    * Envia os resultados para a API Gemini gerar a resposta final.
4.  A resposta é enviada de volta pela mesma rota até ser exibida ao usuário.

---

## Instalação e Configuração

### Pré-requisitos

* Servidor web com PHP (ex: WampServer, XAMPP, Apache).
* Python 3.9 ou superior instalado na máquina do backend.
* Acesso aos dois bancos de dados MySQL.
* Uma chave de API do Google Gemini válida e com faturamento ativado.

### Backend (Servidor Python)

1.  Clone o repositório:
    ```bash
    git clone [URL_DO_SEU_REPOSITORIO]
    cd [PASTA_DO_BACKEND]
    ```

2.  Crie e ative um ambiente virtual:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate  # No Windows
    ```

3.  Instale as dependências: Crie um arquivo `requirements.txt` com o seguinte conteúdo:
    ```
    Flask
    google-generativeai
    mysql-connector-python
    waitress
    python-dotenv
    ```
    E instale com o pip:
    ```bash
    pip install -r requirements.txt
    ```

4.  Configure as variáveis de ambiente: Crie um arquivo chamado `.env` na pasta do backend e adicione suas credenciais. Nunca adicione este arquivo ao Git.

    Arquivo `.env`:
    ```
    # Chave da API do Google Gemini
    GEMINI_API_KEY="SUA_CHAVE_API_AQUI"

    # Credenciais do Banco de Dados do Site
    SITE_DB_HOST="SEU_HOST"
    SITE_DB_USER="USER"
    SITE_DB_PASS="PASS"
    SITE_DB_NAME="DB"

    # Credenciais do Banco de Dados dos PDFs
    PDF_DB_HOST="SEU_HOST"
    PDF_DB_USER="USER"
    PDF_DB_PASS="PASS"
    PDF_DB_NAME="DB"
    ```
    *Lembre-se de adaptar seu arquivo `app.py` para carregar essas variáveis usando uma biblioteca como `python-dotenv`.*
---

## Executando em Produção (Windows)

Para executar o backend de forma estável em um servidor Windows, não use `flask.run()`. A abordagem recomendada é usar o servidor Waitress e gerenciá-lo como um serviço do Windows com o NSSM.

1.  Crie um "runner" para o Waitress: Crie um arquivo `runner.py` na pasta do seu backend.
    ```python
    # runner.py
    from waitress import serve
    from app import app # Supondo que seu arquivo Flask se chame app.py

    serve(app, host='0.0.0.0', port=5000)
    ```

2.  Use o NSSM (Non-Sucking Service Manager):
    * Baixe o NSSM e coloque-o em um local acessível.
    * Abra o prompt de comando como administrador e navegue até a pasta do NSSM.
    * Execute o comando para instalar o serviço:
        ```bash
        nssm install BuscaInteligente
        ```
    * Uma interface gráfica irá aparecer. Configure os seguintes campos:
        * Application Path: O caminho para o `python.exe` dentro da sua pasta `venv`. Ex: `C:\caminho\para\seu_projeto\venv\Scripts\python.exe`
        * Startup directory: A pasta raiz do seu projeto de backend. Ex: `C:\caminho\para\seu_projeto`
        * Arguments: O nome do seu script runner. Ex: `runner.py`
    * Clique em "Install service".

3.  Inicie o serviço:
    ```bash
    nssm start BuscaInteligente
    ```
    Isso garantirá que seu chatbot Python inicie com o Windows e seja reiniciado automaticamente se falhar.

---

## Autor

Desenvolvido por FB Design

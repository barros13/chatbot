import traceback
import re
import json
import mysql.connector
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from google.api_core.exceptions import ResourceExhausted
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES GLOBAIS ---

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
generation_config = genai.GenerationConfig(response_mime_type="application/json")
model = genai.GenerativeModel("gemini-2.5-flash", generation_config=generation_config)
cache_respostas = {}
DB_CONFIG_PDFS = {
    'host': os.getenv("DB_PDF_HOST"),
    'user': os.getenv("DB_PDF_USER"),
    'password': os.getenv("DB_PDF_PASSWORD"),
    'database': os.getenv("DB_PDF_NAME")
}

DB_CONFIG_SITE = {
    'host': os.getenv("DB_SITE_HOST"),
    'user': os.getenv("DB_SITE_USER"),
    'password': os.getenv("DB_SITE_PASSWORD"),
    'database': os.getenv("DB_SITE_NAME")
}

BASE_URL = os.getenv("BASE_URL")

# --- FUNÇÕES AUXILIARES ---

def gerar_link_site(doc):
    categoria, modalidade, ano, arquivo_num, arquivo_nome, doc_id, titulo = (doc.get(k) for k in
                                                                             ['categoria', 'modalidade', 'arquivo_ano',
                                                                              'arquivo_numero', 'arquivo_nome', 'id',
                                                                              'titulo'])
    titulo = (titulo or '').replace(' ', '_').lower()
    if categoria == "licitacoes": return f"{BASE_URL}{modalidade}?setor={categoria}&modalidade={modalidade}&ano={ano}&arquivo={arquivo_num}"
    if categoria in ["licitacoes_extra",
                     "publicacoes_transparencia"]: return f"{BASE_URL}{modalidade}?setor={categoria}&modalidade={modalidade}&ano={ano}&arquivo={arquivo_nome}"
    if categoria == "noticias":
        data_pub = doc.get('data_publicacao').strftime('%d-%m-%Y') if doc.get('data_publicacao') else ''
        return f"{BASE_URL}{categoria}?id={doc_id}&secretaria={modalidade}&data={data_pub}&titulo={titulo}"
    return f"{BASE_URL}{doc.get('url')}"


def analisar_intenção_com_ia(prompt_usuario):
    print(f"INFO: Analisando intenção da busca para: '{prompt_usuario}'")
    prompt_analise = f"""
    Analise a pergunta do usuário e extraia o assunto principal e as palavras-chave de contexto.
    O "assunto_principal" deve ser o objeto específico da busca.
    O "contexto" deve conter termos mais genéricos.
    Retorne o resultado como um objeto JSON com as chaves "assunto_principal" e "contexto".

    Exemplo 1:
    Pergunta: "licitação ar condicionado 2025"
    Resultado: {{"assunto_principal": "ar condicionado", "contexto": ["licitação", "2025"]}}

    Exemplo 2:
    Pergunta: "ponto facultativo carnaval"
    Resultado: {{"assunto_principal": "ponto facultativo", "contexto": ["carnaval"]}}
    ---
    Pergunta do usuário: "{prompt_usuario}"
    Resultado:
    """
    try:
        response = model.generate_content(prompt_analise, request_options={'timeout': 15})
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        search_terms = json.loads(cleaned_text)
        print(f"INFO: Intenção analisada: {search_terms}")
        return search_terms
    except (json.JSONDecodeError, Exception) as e:
        print(f"[AVISO] Falha ao analisar intenção com IA. Usando busca padrão. Erro: {e}")
        return {"assunto_principal": prompt_usuario, "contexto": []}


def processar_resposta_final_com_ia(prompt_usuario, documentos_brutos, cursor_pdf):
    if not documentos_brutos:
        return {
            "resposta": "Não encontrei resultados para os termos informados. Dica: tente usar outras palavras-chave ou verificar a ortografia.",
            "documentos_utilizados": []}

    print(f"INFO: Enviando {len(documentos_brutos)} documentos para a IA gerar a resposta final...")

    contexto_para_ia, documentos_enriquecidos = [], []
    for i, doc in enumerate(documentos_brutos):
        doc['doc_id'] = i
        conteudo_para_ia = (doc.get('descricao') or doc.get('conteudo') or '')[:500].strip().replace('\n', ' ')
        origem = doc['categoria'].replace('_', ' ').title()
        nome_arquivo_pdf = doc.get('arquivo_nome')
        if nome_arquivo_pdf and 'publicacoes' in doc['categoria']:
            cursor_pdf.execute("SELECT texto FROM pdf_documentos WHERE nome_arquivo = %s LIMIT 1", (nome_arquivo_pdf,))
            resultado_pdf = cursor_pdf.fetchone()
            if resultado_pdf:
                conteudo_para_ia = resultado_pdf['texto'][:2500].replace(chr(0), ' ')
                origem = "Documento PDF"
        doc.update({'conteudo_enriquecido': conteudo_para_ia, 'origem_final': origem})
        documentos_enriquecidos.append(doc)
        contexto_para_ia.append({"id": i, "titulo": doc['titulo'], "conteudo": conteudo_para_ia})

    prompt_final = f"""
    Sua tarefa é agir como um assistente de busca inteligente. Analise a pergunta do usuário e a lista de documentos fornecida.

    **Processo:**
    1.  Filtre a Relevância: Selecione APENAS os documentos da lista que são REALMENTE relevantes para a resposta.
    2.  Gere a Resposta: Usando SOMENTE os documentos que você filtrou, formule uma resposta clara e concisa.

    **Formato da Saída:**
    Sua resposta final DEVE ser um objeto JSON com duas chaves:
    -   `"resposta"`: Uma string contendo o texto da resposta.
    -   `"documentos_utilizados"`: Um array contendo APENAS os IDs numéricos dos documentos que você usou.
    
    **Regras da Saída:**
    Sua resposta final não DEVE conter números de documentos:
    Exemplo 1: 
    Saída Incorreta: Processo Seletivo de Contratação Temporária de Motoristas (documento 11)
    Saída CORRETA: Processo Seletivo de Contratação Temporária de Motoristas 
    
    ---
    **Pergunta do Usuário:** "{prompt_usuario}"
    **Lista de Documentos:**
    {json.dumps(contexto_para_ia, indent=2, ensure_ascii=False)}
    """
    try:
        response = model.generate_content(prompt_final, request_options={'timeout': 45})
        resultado_json = json.loads(response.text)
        print("INFO: IA retornou uma resposta estruturada com sucesso.")

        ids_documentos_usados = resultado_json.get("documentos_utilizados", [])
        documentos_finais = [
            {'nome': documentos_enriquecidos[i]['titulo'], 'link': gerar_link_site(documentos_enriquecidos[i]),
             'origem': documentos_enriquecidos[i]['origem_final']} for i in ids_documentos_usados if
            isinstance(i, int) and i < len(documentos_enriquecidos)]

        resultado_json['documentos_finais'] = documentos_finais
        return resultado_json
    except (json.JSONDecodeError, Exception) as e:
        print(f"[ERRO] Falha na chamada final à IA: {e}")
        return {"erro": "ApiError", "mensagem": "Ocorreu um erro ao processar sua solicitação na IA."}


# --- ROTA PRINCIPAL DA API ---

@app.route('/api/perguntar', methods=['GET', 'OPTIONS'])
@cross_origin()
def perguntar():
    prompt_usuario_original = request.args.get('q', '').strip().lower()
    if not prompt_usuario_original: return jsonify({'resposta': 'Pergunta vazia.', 'links': [], 'codigo': 400})
    if prompt_usuario_original in cache_respostas: return jsonify(cache_respostas[prompt_usuario_original])

    print(f"INFO: Cache miss. Processando nova pergunta: '{prompt_usuario_original}'")

    conn_pdf, conn_site = None, None
    try:
        conn_pdf = mysql.connector.connect(**DB_CONFIG_PDFS)
        conn_site = mysql.connector.connect(**DB_CONFIG_SITE)
        cursor_pdf = conn_pdf.cursor(dictionary=True)
        cursor_site = conn_site.cursor(dictionary=True)

        termos_de_busca = analisar_intenção_com_ia(prompt_usuario_original)
        assunto_principal = termos_de_busca.get('assunto_principal', prompt_usuario_original)
        contexto_busca = termos_de_busca.get('contexto', [])

        documentos_encontrados = {}
        colunas = "id, categoria, titulo, descricao, conteudo, url, modalidade, arquivo_nome, arquivo_ano, data_publicacao, arquivo_numero"
        tabelas_e_campos = {
            "paginas": ["titulo", "descricao", "conteudo"],
            "publicacoes_transparencia": ["titulo", "descricao", "conteudo"],
            "noticias": ["titulo", "descricao", "conteudo"],
            "licitacoes": ["titulo", "descricao", "conteudo"],
            "conselhos": ["titulo", "descricao", "conteudo"]
        }

        # Etapa 1: Busca de Alta Prioridade (LIKE no assunto_principal)
        termo_like = f"%{assunto_principal}%"
        print(f"INFO: Buscando com ALTA PRIORIDADE (LIKE): '{termo_like}'")
        for tabela, campos in tabelas_e_campos.items():
            like_conditions = " OR ".join([f"`{campo}` LIKE %s" for campo in campos])
            query = f"SELECT {colunas} FROM `{tabela}` WHERE {like_conditions} LIMIT 5"
            params = (termo_like,) * len(campos)
            cursor_site.execute(query, params)
            for doc in cursor_site.fetchall():
                unique_id = f"{tabela}_{doc['id']}"
                if unique_id not in documentos_encontrados:
                    documentos_encontrados[unique_id] = doc

        # Etapa 2: Busca de Contexto (FULLTEXT nas palavras de contexto)
        if len(documentos_encontrados) < 15 and contexto_busca:
            termo_fulltext = ' '.join(contexto_busca)
            print(f"INFO: Buscando por CONTEXTO (FULLTEXT): '{termo_fulltext}'")

            # Respeitando os índices FULLTEXT de cada tabela
            queries = [
                f"(SELECT {colunas} FROM paginas WHERE MATCH(titulo,descricao) AGAINST (%s IN NATURAL LANGUAGE MODE))",
                f"(SELECT {colunas} FROM publicacoes_transparencia WHERE MATCH(titulo,descricao,conteudo) AGAINST (%s IN NATURAL LANGUAGE MODE))",
                f"(SELECT {colunas} FROM noticias WHERE MATCH(titulo,descricao,conteudo) AGAINST (%s IN NATURAL LANGUAGE MODE))",
                f"(SELECT {colunas} FROM licitacoes WHERE MATCH(titulo,descricao,conteudo) AGAINST (%s IN NATURAL LANGUAGE MODE))",
                f"(SELECT {colunas} FROM conselhos WHERE MATCH(titulo,descricao,conteudo) AGAINST (%s IN NATURAL LANGUAGE MODE))"
            ]
            consulta_fulltext = " UNION ALL ".join(queries) + " LIMIT 15"
            params_fulltext = (termo_fulltext,) * len(queries)

            cursor_site.execute(consulta_fulltext, params_fulltext)
            for doc in cursor_site.fetchall():
                unique_id = f"{doc['categoria']}_{doc['id']}"
                if unique_id not in documentos_encontrados:
                    documentos_encontrados[unique_id] = doc

        lista_documentos = list(documentos_encontrados.values())

        resultado_ia = processar_resposta_final_com_ia(prompt_usuario_original, lista_documentos, cursor_pdf)

        if "erro" in resultado_ia:
            return jsonify({'resposta': resultado_ia["mensagem"], 'links': [], 'codigo': 500})

        resposta_final = {'resposta': resultado_ia.get("resposta", "Não foi possível gerar uma resposta."),
                          'links': resultado_ia.get("documentos_finais", []), 'codigo': 200}
        cache_respostas[prompt_usuario_original] = resposta_final
        return jsonify(resposta_final)

    except Exception as e:
        print(f"[ERRO GERAL] {e}\n{traceback.format_exc()}")
        return jsonify(
            {'resposta': 'Ocorreu um erro interno ao processar sua solicitação.', 'links': [], 'codigo': 500})

    finally:
        if conn_pdf: conn_pdf.close()
        if conn_site: conn_site.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

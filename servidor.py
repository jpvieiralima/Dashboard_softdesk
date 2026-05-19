import json
import os
import sys
import time
import threading
import sqlite3
import logging
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import Flask, request, jsonify, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chamados.db")

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-me-in-production')

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def carregar_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        sys.exit(1)

CONFIG = carregar_config()
BASE_URL = CONFIG.get("softdesk_url", "").rstrip("/")
HASH_API = CONFIG.get("hash_api", "")
PORTA = CONFIG.get("porta_servidor", 5000)
INTERVALO = CONFIG.get("intervalo_atualizacao_segundos", 120)

dados_cache_memoria = {}

def safe_get(d, key, subkey, default):
    if not isinstance(d, dict): return default
    val = d.get(key)
    if isinstance(val, dict): return val.get(subkey, default)
    return default

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS chamados (codigo INTEGER PRIMARY KEY, status TEXT, data_abertura TEXT, json_data TEXT)')
    
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        must_change_pw INTEGER NOT NULL DEFAULT 0
    )''')
    
    admin = c.execute("SELECT * FROM usuarios WHERE username = 'admin'").fetchone()
    if not admin:
        hash_pw = generate_password_hash('adminadmin')
        c.execute("INSERT INTO usuarios (username, password_hash, role, must_change_pw) VALUES (?, ?, 'admin', 1)", ('admin', hash_pw))
        print("  [SEGURANÇA] Usuário 'admin' criado com sucesso. Senha temporária: adminadmin")
        
    conn.commit()
    conn.close()

def limpar_virada_de_mes(conn):
    mes_atual_str = datetime.now().strftime("%Y-%m") 
    mes_atual_br = datetime.now().strftime("%m/%Y")
    
    c = conn.cursor()
    c.execute("SELECT codigo, status, data_abertura FROM chamados")
    todos = c.fetchall()
    
    removidos = 0
    palavras_mortas = ['concluído', 'concluido', 'fechado', 'cancelado', 'excluído', 'excluido', 'encerrado']
    
    for row in todos:
        cod, status, data_abertura = row
        data_str = str(data_abertura)
        
        # Ignora a limpeza se o chamado for deste mês (para manter o contador de "Encerrados" ativo)
        if mes_atual_str in data_str or mes_atual_br in data_str:
            continue
            
        # Se for de meses anteriores, avalia o status: só apagamos se já estiver fechado
        status_lower = str(status).lower()
        if any(p in status_lower for p in palavras_mortas):
            c.execute("DELETE FROM chamados WHERE codigo = ?", (cod,))
            removidos += 1
            
    conn.commit()
    if removidos > 0:
        print(f"  [LIMPEZA OTIMIZADA] {removidos} chamados fechados antigos foram apagados da memória.")

def api_get(endpoint):
    url = f"{BASE_URL}/api/api.php/{endpoint}"
    headers = {"hash-api": HASH_API, "Accept": "application/json"}
    for _ in range(3):
        try:
            req = Request(url, headers=headers, method="GET")
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429:
                time.sleep(5)
                continue
            return None
        except URLError:
            return None
    return None

def buscar_chamado_por_codigo(codigo):
    resp = api_get(f"chamado?codigo={codigo}")
    if resp and "objeto" in resp: return resp["objeto"]
    return None

def salvar_ou_atualizar_chamado(chamado, conn):
    c = conn.cursor()
    codigo = chamado.get("codigo")
    status_desc = safe_get(chamado, "status", "descricao", "Sem status")
    data_ab = chamado.get("data_abertura", "")
    json_str = json.dumps(chamado, ensure_ascii=False)
    c.execute('''INSERT INTO chamados (codigo, status, data_abertura, json_data) VALUES (?, ?, ?, ?)
                 ON CONFLICT(codigo) DO UPDATE SET status=excluded.status, data_abertura=excluded.data_abertura, json_data=excluded.json_data''', 
              (codigo, status_desc, data_ab, json_str))
    conn.commit()

def sincronizar_dados():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando sincronização...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT codigo FROM chamados WHERE status NOT IN ('Concluído', 'Cancelado', 'Fechado')")
    pendentes = [row[0] for row in c.fetchall()]
    if pendentes:
        print(f"  Atualizando o status de {len(pendentes)} chamados em andamento...")
        for cod in pendentes:
            ch = buscar_chamado_por_codigo(cod)
            if ch: 
                salvar_ou_atualizar_chamado(ch, conn)
            else:
                c_del = conn.cursor()
                c_del.execute("UPDATE chamados SET status = 'Excluído' WHERE codigo = ?", (cod,))
                conn.commit()
            time.sleep(0.3)

    c.execute("SELECT MAX(codigo) FROM chamados")
    max_codigo = c.fetchone()[0]
    if not max_codigo: max_codigo = 19048 

    codigo_teste = max_codigo + 1
    falhas_consecutivas = 0
    while falhas_consecutivas < 5: 
        novo_chamado = buscar_chamado_por_codigo(codigo_teste)
        if novo_chamado:
            salvar_ou_atualizar_chamado(novo_chamado, conn)
            falhas_consecutivas = 0
            codigo_teste += 1
            time.sleep(0.3)
        else:
            falhas_consecutivas += 1
            codigo_teste += 1
            time.sleep(0.1)

    limpar_virada_de_mes(conn)
    gerar_cache_dashboard(conn)
    conn.close()
    print(f"  Sincronização finalizada.")

def gerar_cache_dashboard(conn):
    global dados_cache_memoria
    c = conn.cursor()
    
    # CORREÇÃO CRÍTICA: Removido o filtro de 'data_abertura'. 
    # Agora puxa TUDO do banco. O 'limpar_virada_de_mes' já garantiu que os fechados antigos fossem apagados.
    c.execute("SELECT json_data FROM chamados")
    todos_chamados = [json.loads(row[0]) for row in c.fetchall() if row[0]]

    def compilar_metricas(lista_filtrada):
        chamados_por_status = {}
        chamados_por_atendente = {}
        atendentes_set = set()
        chamados_normalizados = []
        
        for ch in lista_filtrada:
            if not isinstance(ch, dict): continue

            status_desc = safe_get(ch, "status", "descricao", "Sem status")
            status_cod = safe_get(ch, "status", "codigo", 0)
            atend_nome = safe_get(ch, "atendente", "nome", "Sem atendente")
            usuario_nome = safe_get(ch, "usuario", "nome", "Sistema")
            
            area_desc = safe_get(ch, "area", "descricao", "-")
            cliente_nome = safe_get(ch, "cliente", "nome", "-")
            servico_desc = safe_get(ch, "servico", "descricao", "-")
            
            solicitante = "-"
            if "solicitante" in ch and isinstance(ch["solicitante"], dict):
                solicitante = ch["solicitante"].get("nome", "-")
            elif "usuario" in ch and isinstance(ch["usuario"], dict):
                solicitante = ch["usuario"].get("nome", "-")

            if atend_nome != "Sem atendente":
                atendentes_set.add(atend_nome)
                chamados_por_atendente[atend_nome] = chamados_por_atendente.get(atend_nome, 0) + 1

            key_status = f"{status_cod}_{status_desc}"
            if key_status not in chamados_por_status:
                chamados_por_status[key_status] = {"descricao": status_desc, "quantidade": 0, "chamados": []}
            
            chamados_por_status[key_status]["quantidade"] += 1
            chamados_por_status[key_status]["chamados"].append({"titulo": ch.get("titulo", "")})
            
            chamados_normalizados.append({
                "codigo": ch.get("codigo"),
                "titulo": ch.get("titulo", ""),
                "data_abertura": ch.get("data_abertura", ""),
                "hora_abertura": ch.get("hora_abertura", ""),
                "atendente": atend_nome,
                "usuario": usuario_nome,
                "solicitante": solicitante,
                "area": area_desc,
                "cliente": cliente_nome,
                "servico": servico_desc,
                "status": status_desc
            })

        chamados_normalizados.sort(key=lambda x: x.get("codigo", 0), reverse=True)
        lista_atendentes = [{"nome": n, "chamados_abertos": chamados_por_atendente.get(n, 0)} for n in atendentes_set]

        return {
            "total_chamados": len(lista_filtrada),
            "todos_chamados": chamados_normalizados,
            "chamados_por_status": chamados_por_status,
            "atendentes": lista_atendentes
        }

    lista_suporte, lista_bpo, lista_servicos = [], [], []

    for ch in todos_chamados:
        if not isinstance(ch, dict): continue
        area_atual = safe_get(ch, "area", "descricao", "").strip().upper()

        if area_atual == "BPO":
            lista_bpo.append(ch)
        elif area_atual == "SERVIÇOS & PROJETOS":
            lista_servicos.append(ch)
        else:
            lista_suporte.append(ch)

    dados_cache_memoria = {
        "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "suporte": compilar_metricas(lista_suporte),
        "bpo": compilar_metricas(lista_bpo),
        "servicos": compilar_metricas(lista_servicos),
        "erro": None
    }

def loop_atualizacao():
    while True:
        try: sincronizar_dados()
        except Exception as e: dados_cache_memoria["erro"] = str(e)
        time.sleep(INTERVALO)

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'username': session['username'],
            'role': session['role'],
            'must_change_pw': session.get('must_change_pw', False)
        })
    return jsonify({'logged_in': False}), 401

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['must_change_pw'] = bool(user['must_change_pw'])
        return jsonify({'success': True, 'must_change_pw': session['must_change_pw'], 'role': session['role']})
    
    return jsonify({'success': False, 'message': 'Usuário ou senha incorretos'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    new_password = request.json.get('new_password')
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'message': 'A senha deve ter no mínimo 6 caracteres'}), 400
        
    hash_pw = generate_password_hash(new_password)
    conn = get_db()
    conn.execute("UPDATE usuarios SET password_hash = ?, must_change_pw = 0 WHERE id = ?", (hash_pw, session['user_id']))
    conn.commit()
    conn.close()
    
    session['must_change_pw'] = False
    return jsonify({'success': True})

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
def manage_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
        
    conn = get_db()
    if request.method == 'GET':
        users = conn.execute("SELECT id, username, role FROM usuarios").fetchall()
        conn.close()
        return jsonify([dict(u) for u in users])
        
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'user')
        
        try:
            hash_pw = generate_password_hash(password)
            conn.execute("INSERT INTO usuarios (username, password_hash, role, must_change_pw) VALUES (?, ?, ?, 1)", (username, hash_pw, role))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'message': 'Este usuário já existe no sistema'}), 400
            
    if request.method == 'DELETE':
        user_id = request.json.get('id')
        if user_id == session['user_id']:
            conn.close()
            return jsonify({'success': False, 'message': 'Você não pode deletar a si mesmo'}), 400
        
        conn.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/dados')
def api_dados():
    if 'user_id' not in session or session.get('must_change_pw'):
        return jsonify({'error': 'Não autorizado'}), 401
    return jsonify(dados_cache_memoria)

@app.route('/')
def serve_dashboard():
    return send_file('dashboard.html')

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    init_db()
    
    threading.Thread(target=loop_atualizacao, daemon=True).start()
    time.sleep(2)
    
    print(f"Servidor Flask Iniciado! Acesse: http://localhost:{PORTA}")
    app.run(host='0.0.0.0', port=PORTA, debug=False, use_reloader=False)
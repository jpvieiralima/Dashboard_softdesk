# Dashboard - Guia de Setup

Dashboard em tempo real para monitoramento de chamados Softdesk.

## Pré-requisitos

- Python 3.8+
- pip

## Instalação

### 1. Clonar o repositório
```bash
git clone https://github.com/seu-usuario/dashboard.git
cd dashboard
```

### 2. Criar ambiente virtual
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Instalar dependências
```bash
pip install flask werkzeug
```

### 4. Configurar credenciais
```bash
cp config.json config.json.bak
```

Edite `config.json` e adicione:
- `softdesk_url`: URL base do seu Softdesk
- `hash_api`: Token de API (obtido em: Administração > Configurações > API)
- `porta_servidor`: Porta desejada (padrão: 5000)

### 5. Executar
```bash
python servidor.py
```

Acesse em `http://localhost:5000`

### Credenciais padrão
- Usuário: `admin`
- Senha: `adminadmin`

⚠️ **Importante**: Altere a senha na primeira execução.

## Estrutura

- `servidor.py` - Backend Flask
- `dashboard.html` - Frontend
- `chamados.db` - Banco de dados (gerado automaticamente)
- `config.json` - Configurações

## Segurança

- Nunca compartilhe `config.json` com suas credenciais
- Use variáveis de ambiente em produção
- Altere `FLASK_SECRET_KEY` antes de usar em produção


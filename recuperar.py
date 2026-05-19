import sqlite3

# Conecta ao banco de dados atual
conn = sqlite3.connect('chamados.db')

# Deleta APENAS a tabela de chamados (mantém a de usuários intacta)
conn.execute('DROP TABLE IF EXISTS chamados')
conn.commit()
conn.close()

print("Tabela de chamados limpa com sucesso!")
print("Os logins e senhas foram mantidos.")
print("Você já pode iniciar o servidor.py novamente.")
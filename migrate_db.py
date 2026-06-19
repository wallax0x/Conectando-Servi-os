import sqlite3
import os

def migrate():
    # Caminho do banco de dados (ajustado para o padrão do seu projeto)
    db_path = 'instance/database.db'
    
    if not os.path.exists(db_path):
        print(f"Erro: Arquivo {db_path} não encontrado.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"Verificando estrutura da tabela 'users' em {db_path}...")
        
        # Tenta adicionar a coluna profile_image
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN profile_image TEXT")
            conn.commit()
            print("Sucesso: Coluna 'profile_image' adicionada à tabela 'users'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Aviso: A coluna 'profile_image' já existe.")
            else:
                raise e
                
        conn.close()
        print("Migração concluída com sucesso!")
        
    except Exception as e:
        print(f"Erro durante a migração: {e}")

if __name__ == "__main__":
    migrate()

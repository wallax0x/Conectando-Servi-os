from app import app, db
from models import User

def fix_cities_to_garanhuns():
    """
    Regionaliza todos os usuários e profissionais para Garanhuns, PE.
    Focado no MVP regional.
    """
    with app.app_context():
        print("Iniciando regionalização dos dados para Garanhuns/PE...")
        
        # Seleciona todos os usuários
        users = User.query.all()
        count = 0
        
        for user in users:
            user.city = "Garanhuns"
            user.state = "PE"
            count += 1
            
        db.session.commit()
        print(f"Sucesso! {count} usuários foram atualizados para Garanhuns, PE.")

if __name__ == "__main__":
    fix_cities_to_garanhuns()

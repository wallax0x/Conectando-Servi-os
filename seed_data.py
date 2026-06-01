from app import app, db
from models import User, ServiceCategory, Professional, Review, ServiceRequest
from werkzeug.security import generate_password_hash

def seed_database():
    with app.app_context():
        print("Limpando banco de dados...")
        db.drop_all()
        db.create_all()
        
        print("Criando categorias de serviços...")
        categories = [
            ServiceCategory(name='Reformas e Reparos', icon='fa-hammer', description='Pedreiros, pintores, eletricistas, encanadores'),
            ServiceCategory(name='Serviços Domésticos', icon='fa-home', description='Limpeza, jardinagem, organização'),
            ServiceCategory(name='Tecnologia', icon='fa-laptop', description='Informática, sites, suporte técnico'),
            ServiceCategory(name='Aulas Particulares', icon='fa-book', description='Professores de idiomas, matemática, música'),
            ServiceCategory(name='Beleza e Estética', icon='fa-cut', description='Cabeleireiros, manicures, maquiadores'),
            ServiceCategory(name='Saúde e Bem-estar', icon='fa-heartbeat', description='Personal trainers, nutricionistas, fisioterapeutas'),
            ServiceCategory(name='Eventos', icon='fa-birthday-cake', description='Fotógrafos, músicos, buffet'),
            ServiceCategory(name='Transporte', icon='fa-truck', description='Mudanças, entregas, motoristas'),
        ]
        
        for category in categories:
            db.session.add(category)
        
        db.session.commit()
        print(f"{len(categories)} categorias criadas!")
        
        print("Criando profissionais de exemplo...")
        
        professionals_data = [
            {
                'name': 'João Silva',
                'email': 'joao.silva@example.com',
                'cpf': '123.456.789-01',
                'phone': '(11) 98765-4321',
                'cep': '01310100',
                'address': 'Avenida Paulista',
                'neighborhood': 'Bela Vista',
                'city': 'São Paulo',
                'state': 'SP',
                'category': 'Reformas e Reparos',
                'bio': 'Pedreiro com mais de 15 anos de experiência em reformas residenciais e comerciais. Especialista em alvenaria, acabamento e pequenos reparos.',
                'experience_years': 15,
                'starting_price': 150.00
            },
            {
                'name': 'Maria Santos',
                'email': 'maria.santos@example.com',
                'cpf': '987.654.321-09',
                'phone': '(11) 91234-5678',
                'cep': '01310100',
                'address': 'Avenida Paulista',
                'neighborhood': 'Bela Vista',
                'city': 'São Paulo',
                'state': 'SP',
                'category': 'Serviços Domésticos',
                'bio': 'Profissional de limpeza residencial e comercial. Trabalho com produtos ecológicos e técnicas modernas de limpeza profunda.',
                'experience_years': 8,
                'starting_price': 80.00
            },
            {
                'name': 'Carlos Mendes',
                'email': 'carlos.mendes@example.com',
                'cpf': '456.789.123-45',
                'phone': '(21) 98888-7777',
                'cep': '20040020',
                'address': 'Avenida Rio Branco',
                'neighborhood': 'Centro',
                'city': 'Rio de Janeiro',
                'state': 'RJ',
                'category': 'Tecnologia',
                'bio': 'Desenvolvedor web e designer gráfico. Criação de sites, logos e identidade visual para empresas de todos os tamanhos.',
                'experience_years': 10,
                'starting_price': 500.00
            },
            {
                'name': 'Ana Paula',
                'email': 'ana.paula@example.com',
                'cpf': '321.654.987-65',
                'phone': '(11) 97777-6666',
                'cep': '04543011',
                'address': 'Avenida Brigadeiro Faria Lima',
                'neighborhood': 'Itaim Bibi',
                'city': 'São Paulo',
                'state': 'SP',
                'category': 'Aulas Particulares',
                'bio': 'Professora de inglês certificada com experiência internacional. Aulas para todos os níveis, preparatório para certificações.',
                'experience_years': 12,
                'starting_price': 100.00
            },
            {
                'name': 'Pedro Oliveira',
                'email': 'pedro.oliveira@example.com',
                'cpf': '789.123.456-78',
                'phone': '(11) 96666-5555',
                'cep': '01310100',
                'address': 'Avenida Paulista',
                'neighborhood': 'Bela Vista',
                'city': 'São Paulo',
                'state': 'SP',
                'category': 'Reformas e Reparos',
                'bio': 'Eletricista profissional com especialização em instalações residenciais e comerciais. Atendo emergências 24h.',
                'experience_years': 18,
                'starting_price': 120.00
            },
            {
                'name': 'Juliana Costa',
                'email': 'juliana.costa@example.com',
                'cpf': '654.321.789-32',
                'phone': '(21) 95555-4444',
                'cep': '22640102',
                'address': 'Avenida das Américas',
                'neighborhood': 'Barra da Tijuca',
                'city': 'Rio de Janeiro',
                'state': 'RJ',
                'category': 'Beleza e Estética',
                'bio': 'Cabeleireira e maquiadora profissional. Atendimento em domicílio para eventos especiais, casamentos e festas.',
                'experience_years': 7,
                'starting_price': 150.00
            }
        ]
        
        for prof_data in professionals_data:
            category = ServiceCategory.query.filter_by(name=prof_data['category']).first()
            
            user = User(
                name=prof_data['name'],
                email=prof_data['email'],
                cpf=prof_data['cpf'],
                password_hash=generate_password_hash('senha123'),
                user_type='professional',
                phone=prof_data['phone'],
                cep=prof_data['cep'],
                address=prof_data['address'],
                neighborhood=prof_data['neighborhood'],
                city=prof_data['city'],
                state=prof_data['state']
            )
            db.session.add(user)
            db.session.flush()
            
            professional = Professional(
                user_id=user.id,
                category_id=category.id,
                bio=prof_data['bio'],
                experience_years=prof_data['experience_years'],
                starting_price=prof_data['starting_price'],
                verified=True,
                response_time='24 horas'
            )
            db.session.add(professional)
        
        db.session.commit()
        print(f"{len(professionals_data)} profissionais criados!")
        
        print("Criando cliente de exemplo...")
        client = User(
            name='Cliente Teste',
            email='cliente@example.com',
            cpf='111.222.333-44',
            password_hash=generate_password_hash('senha123'),
            user_type='client',
            phone='(11) 94444-3333',
            cep='01310100',
            address='Avenida Paulista',
            neighborhood='Bela Vista',
            city='São Paulo',
            state='SP'
        )
        db.session.add(client)
        db.session.commit()
        print("Cliente criado!")
        
        print("Adicionando solicitações e avaliações de exemplo...")
        prof1 = Professional.query.first()
        
        # Criar um request primeiro para poder avaliar
        request1 = ServiceRequest(
            client_id=client.id,
            professional_id=prof1.id,
            title='Conserto de Vazamento',
            description='Tem um vazamento na pia da cozinha.',
            status='concluido',
            final_price=150.0
        )
        db.session.add(request1)
        db.session.commit()

        reviews = [
            Review(request_id=request1.id, professional_id=prof1.id, client_id=client.id, rating=5, comment='Excelente profissional! Muito pontual e trabalho de qualidade.'),
            Review(request_id=request1.id, professional_id=prof1.id, client_id=client.id, rating=4, comment='Bom trabalho, recomendo!')
        ]
        
        for review in reviews:
            db.session.add(review)
        
        db.session.commit()
        print("Avaliações criadas!")
        
        print("\n=== DADOS DE EXEMPLO CRIADOS COM SUCESSO ===")
        print("\nContas de teste criadas:")
        print("- Profissional: joao.silva@example.com / senha123")
        print("- Cliente: cliente@example.com / senha123")
        print("\nOutros profissionais:")
        for prof_data in professionals_data[1:]:
            print(f"- {prof_data['name']}: {prof_data['email']} / senha123")

if __name__ == '__main__':
    seed_database()

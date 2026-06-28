# app.py - Versão revisada completa (CRUD categorias + front + proteções)
import os
import re
from datetime import datetime, timedelta

import requests
from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from validate_docbr import CPF
from sqlalchemy import or_, func, extract
from functools import wraps
import base64
import json
from utils import censurar_dados
# ---------- Config do Flask ----------
app = Flask(__name__)
# Em produção - use variável de ambiente para SECRET_KEY
app.secret_key = os.environ.get("SECRET_KEY", "uma_chave_muito_secreta")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------- Inicializar DB ----------
try:
    from database import db
except Exception as e:
    raise RuntimeError(
        "Erro ao importar 'db' de database.py. Verifique se existe database.py e contém 'db = SQLAlchemy()'."
    ) from e

db.init_app(app)

# ---------- Importar models ----------
try:
    from models import User, Professional, ServiceCategory, ServiceRequest, Review, Message, Notification
except Exception as e:
    raise RuntimeError(
        "Erro ao importar models. Verifique models.py e ajuste nomes/classes: User, Professional, ServiceCategory, ServiceRequest, Review, Message, Notification."
    ) from e

# ---------- Login manager ----------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None


# ---------- Context Processor para Notificações ----------
@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        unread_notifications = current_user.notifications.filter_by(
            is_read=False).order_by(Notification.created_at.desc()).all()
        return dict(
            unread_notifications_count=len(unread_notifications),
            # Mostra as 5 mais recentes no dropdown
            recent_notifications=unread_notifications[:5]
        )
    return dict(unread_notifications_count=0, recent_notifications=[])


# API para atualizar contagem via polling
@app.route('/api/unread-count')
def unread_count_api():
    if not current_user.is_authenticated:
        return jsonify({'count': 0}), 200
    count = current_user.notifications.filter_by(is_read=False).count()
    return jsonify({'count': count})


@app.route('/ler-notificacao/<int:notif_id>')
@login_required
def read_notification(notif_id):
    notif = db.session.get(Notification, notif_id)
    if notif and notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
        if notif.link:
            return redirect(notif.link)
    return redirect(url_for('dashboard'))


@app.route('/notificacoes/marcar-lidas', methods=['POST'])
@login_required
def marcar_notificacoes_lidas():
    try:
        notificacoes_pendentes = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
        
        for notificacao in notificacoes_pendentes:
            notificacao.is_read = True
            
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Notificações atualizadas'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500



# ---------- CPF validator ----------
cpf_validator = CPF()

# --------------------------
# ADMIN DECORATOR
# --------------------------


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('usuario'):
            return redirect(url_for('admin'))
        return f(*args, **kwargs)
    return decorated_function

# --------------------------
# HELPERS
# --------------------------


def normalize_cpf_masked(cpf_masked: str) -> str:
    """Converte qualquer entrada para formato 000.000.000-00 (se possível)."""
    if not cpf_masked:
        return ''
    digits = re.sub(r'\D', '', cpf_masked)
    if len(digits) != 11:
        return cpf_masked
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def validate_cep_garanhuns(cep: str):
    """Valida via ViaCEP e garante Garanhuns/PE. Retorna dict ou None."""
    if not cep:
        return None
    cep_digits = re.sub(r'\D', '', cep)
    if len(cep_digits) != 8:
        return None
    try:
        r = requests.get(
            f"https://viacep.com.br/ws/{cep_digits}/json/", timeout=5)
        if not r.ok:
            return None
        data = r.json()
        if 'erro' in data:
            return None
        # garante cidade/UF
        if data.get('localidade') != 'Garanhuns' or data.get('uf') != 'PE':
            return None
        return {
            'cep': cep_digits,
            'address': data.get('logradouro', '') or '',
            'neighborhood': data.get('bairro', '') or '',
            'city': data.get('localidade', '') or '',
            'state': data.get('uf', '') or ''
        }
    except Exception:
        return None

# --------------------------
# ROTAS PÚBLICAS / FRONT
# --------------------------


@app.route('/')
def index():
    categoria_id = request.args.get('categoria_id')
    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()
    
    query = Professional.query
    
    if categoria_id and categoria_id.isdigit():
        query = query.filter_by(category_id=int(categoria_id))
        
    professionals = query.order_by(
        Professional.id.desc()).limit(6).all()
        
    return render_template('index.html', categories=categories, professionals=professionals)


# Não esqueça de importar a função de censura no topo do seu app.py
# from utils import censurar_mensagem

# --------------------------
# REGISTRO
# --------------------------
@app.route('/registro', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = (request.form.get('name') or "").strip()
        email = (request.form.get('email') or "").strip().lower()
        cpf_raw = request.form.get('cpf') or ""
        cpf_mask = normalize_cpf_masked(cpf_raw)
        password = request.form.get('password') or ""
        user_type = request.form.get('user_type', 'client')
        phone = (request.form.get('phone') or "").strip()
        cep_raw = request.form.get('cep') or ""

        # validações básicas
        if not name or not email or not password:
            flash('Nome, email e senha são obrigatórios.', 'danger')
            return render_template('register.html')

        digits_only_cpf = re.sub(r'\D', '', cpf_mask)
        if not cpf_mask or not cpf_validator.validate(digits_only_cpf):
            flash('CPF inválido.', 'danger')
            return render_template('register.html')

        cep_data = validate_cep_garanhuns(cep_raw)
        if not cep_data:
            flash('CEP inválido ou fora de Garanhuns-PE.', 'danger')
            return render_template('register.html')

        # verifica duplicidade
        if User.query.filter(or_(User.cpf == cpf_mask, User.email == email)).first():
            flash('CPF ou email já cadastrado.', 'danger')
            return render_template('register.html')

        user = User(
            name=name,
            email=email,
            cpf=cpf_mask,
            password_hash=generate_password_hash(password),
            user_type=user_type,
            phone=phone,
            cep=cep_data['cep'],
            address=cep_data['address'],
            neighborhood=cep_data['neighborhood'],
            city=cep_data['city'],
            state=cep_data['state'],
            created_at=datetime.utcnow()
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)

        if user_type == 'professional':
            return redirect(url_for('complete_professional_profile'))

        return redirect(url_for('index'))

    return render_template('register.html')

# --------------------------
# LOGIN
# --------------------------


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        cpf_raw = request.form.get('cpf') or ""
        cpf_mask = normalize_cpf_masked(cpf_raw)
        password = request.form.get('password') or ""

        user = User.query.filter_by(cpf=cpf_mask).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('CPF ou senha incorretos.', 'danger')

    return render_template('login.html')


@app.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identifier = (request.form.get('identifier') or '').strip()
        # No futuro: implementar lógica de envio de e-mail com token
        flash(f'Se o e-mail ou CPF {identifier} estiver cadastrado, você receberá um link de recuperação em breve.', 'info')
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


# --------------------------
# LOGOUT
# --------------------------


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --------------------------
# SEARCH
# --------------------------


@app.route('/search')
def search():
    name = (request.args.get('name') or '').strip()
    category_id = request.args.get('category', '')
    neighborhood = (request.args.get('neighborhood') or '').strip()
    min_price = (request.args.get('min_price') or '').strip()
    max_price = (request.args.get('max_price') or '').strip()

    # junção segura (Professional tem relationship user via backref)
    query = Professional.query.join(User)

    if name:
        query = query.filter(User.name.ilike(f"%{name}%"))

    if category_id and category_id.isdigit():
        query = query.filter(Professional.category_id == int(category_id))

    if neighborhood:
        query = query.filter(User.neighborhood.ilike(f"%{neighborhood}%"))

    try:
        if min_price:
            query = query.filter(
                Professional.starting_price >= float(min_price))
        if max_price:
            query = query.filter(
                Professional.starting_price <= float(max_price))
    except ValueError:
        # se preço inválido, ignora o filtro
        pass

    professionals = query.all()
    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()
    return render_template('search.html', professionals=professionals, categories=categories)

# --------------------------
# PERFIL DO PROFISSIONAL (PÚBLICO)
# --------------------------


@app.route('/profissional/<int:professional_id>')
def professional_profile(professional_id):
    # Busca o profissional ou retorna 404 se não existir
    prof = Professional.query.get_or_404(professional_id)

    # Busca as avaliações deste profissional para exibir no perfil
    reviews = Review.query.filter_by(professional_id=prof.id).order_by(
        Review.created_at.desc()).all()

    return render_template('professional_profile.html', professional=prof, reviews=reviews)


@app.route('/solicitar-servico/<int:professional_id>', methods=['GET', 'POST'])
@login_required
def request_service(professional_id):
    prof = Professional.query.get_or_404(professional_id)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        budget = request.form.get('budget')
        preferred_date = request.form.get('preferred_date')

        # Aplicando a censura no título e descrição
        title_seguro = censurar_dados(title)
        description_segura = censurar_dados(description)

        try:
            budget_val = float(budget) if budget else None
        except ValueError:
            budget_val = None

        new_request = ServiceRequest(
            client_id=current_user.id,
            professional_id=prof.id,
            title=title_seguro,
            description=description_segura,
            budget=budget_val,
            preferred_date=preferred_date,
            status='pendente',
            created_at=datetime.utcnow()
        )

        db.session.add(new_request)
        db.session.commit()

        flash(
            'Solicitação enviada com sucesso! Aguarde o retorno do profissional.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('request_service.html', professional=prof)


@app.route('/avaliar-profissional/<int:professional_id>', methods=['GET', 'POST'])
@login_required
def review_professional(professional_id):
    prof = Professional.query.get_or_404(professional_id)

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = (request.form.get('comment') or '').strip()

        # Aplicando a censura no comentário
        comment_seguro = censurar_dados(comment)

        last_request = ServiceRequest.query.filter_by(
            client_id=current_user.id,
            professional_id=prof.id
        ).order_by(ServiceRequest.created_at.desc()).first()

        new_review = Review(
            professional_id=prof.id,
            client_id=current_user.id,
            request_id=last_request.id if last_request else 0,
            rating=int(rating) if rating else 5,
            comment=comment_seguro,
            created_at=datetime.utcnow()
        )

        db.session.add(new_review)
        db.session.commit()

        flash('Obrigado pela sua avaliação!', 'success')
        return redirect(url_for('professional_profile', professional_id=prof.id))

    return render_template('review.html', professional=prof)

# --------------------------
# COMPLETAR PERFIL PROFISSIONAL
# --------------------------


@app.route('/completar-perfil-profissional', methods=['GET', 'POST'])
@login_required
def complete_professional_profile():
    if getattr(current_user, 'user_type', None) != 'professional':
        return redirect(url_for('index'))

    # se já existe perfil, redireciona
    if Professional.query.filter_by(user_id=current_user.id).first():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            category_id = int(request.form.get('category_id')
                              ) if request.form.get('category_id') else None
        except ValueError:
            category_id = None

        prof = Professional(
            user_id=current_user.id,
            category_id=category_id,
            bio=censurar_dados((request.form.get('bio') or '').strip()),
            experience_years=int(request.form.get('experience_years')) if request.form.get(
                'experience_years') else None,
            starting_price=float(request.form.get('starting_price')) if request.form.get(
                'starting_price') else None,
            response_time=request.form.get('response_time') or '24 horas',
            created_at=datetime.utcnow()
        )
        # Upload de Foto de Perfil
        if 'foto_perfil' in request.files:
            file = request.files['foto_perfil']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                novo_nome = f"prof_{current_user.id}_{filename}"
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], novo_nome)
                file.save(caminho_salvar)
                prof.profile_photo = novo_nome

        db.session.add(prof)
        db.session.commit()
        flash('Perfil profissional criado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()
    return render_template('complete_profile.html', categories=categories)

# --------------------------
# DASHBOARD
# --------------------------


def limpar_valor_moeda(valor):
    if not valor:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    
    # Limpeza implacável: troca vírgula por ponto e arranca tudo que não for número ou ponto
    valor_bruto = str(valor)
    valor_limpo = re.sub(r'[^0-9.]', '', valor_bruto.replace(',', '.'))
    
    try:
        if valor_limpo:
            return float(valor_limpo)
    except Exception as e:
        print(f"Erro ao converter valor: {valor_bruto} -> {e}")
    return 0.0

@app.route('/dashboard')
@login_required
def dashboard():
    from datetime import timedelta
    if getattr(current_user, 'user_type', None) == 'professional':
        prof = Professional.query.filter_by(user_id=current_user.id).first()
        if not prof:
            return redirect(url_for('complete_professional_profile'))
        
        # Busca todas as solicitações para filtrar via Python (mais robusto contra acentos/case)
        requests_list = ServiceRequest.query.filter_by(
            professional_id=prof.id).order_by(ServiceRequest.created_at.desc()).all()
        
        # Filtros via Python para garantir precisão
        novos_pedidos = sum(1 for r in requests_list if r.status and r.status.upper() in ['PENDENTE', 'PENDING'])
        em_andamento = sum(1 for r in requests_list if r.status and r.status.upper() in ['ACEITO', 'ACCEPTED', 'ORCAMENTO_ENVIADO', 'ORÇAMENTO ENVIADO', 'EM ANDAMENTO'])
        concluidos = sum(1 for r in requests_list if r.status and r.status.upper() in ['CONCLUIDO', 'CONCLUÍDO', 'COMPLETED', 'FINALIZADO'])
        
        # Conversão segura para Total Ganho e Gráfico (Regex implacável)
        total_ganho = 0.0
        meses_labels_full = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        chart_labels = []
        chart_data = [0.0] * 6
        hoje = datetime.now()
        
        # Mapeamento de índices para os últimos 6 meses
        meses_map = {}
        for i in range(5, -1, -1):
            d = hoje - timedelta(days=i*30)
            m_idx = d.month
            chart_labels.append(meses_labels_full[m_idx-1])
            meses_map[m_idx] = 5 - i

        for r in requests_list:
            if r.status and r.status.upper() in ['CONCLUIDO', 'CONCLUÍDO', 'COMPLETED', 'FINALIZADO']:
                valor_bruto = str(r.final_price if r.final_price is not None else (r.budget if r.budget is not None else 0))
                v_float = limpar_valor_moeda(valor_bruto)
                total_ganho += v_float
                
                if r.created_at and r.created_at.month in meses_map:
                    chart_data[meses_map[r.created_at.month]] += v_float

        # Mantendo 'stats' para compatibilidade
        stats = {
            'novos': novos_pedidos,
            'ativos': em_andamento,
            'concluidos': concluidos,
            'total_ganho': total_ganho
        }

        return render_template('professional_dashboard.html', 
                               professional=prof, 
                               requests=requests_list, 
                               stats=stats,
                               novos_pedidos=novos_pedidos,
                               em_andamento=em_andamento,
                               concluidos=concluidos,
                               total_ganho=total_ganho,
                               chart_labels=chart_labels,
                               chart_data=chart_data)
    else:
        import re
        from collections import defaultdict

        # Busca todas as solicitações para filtrar via Python
        todas_solicitacoes = ServiceRequest.query.filter_by(
            client_id=current_user.id).order_by(ServiceRequest.created_at.desc()).all()
        
        total_pendentes = 0
        total_concluidos = 0
        total_investido = 0.0
        gastos_por_categoria = defaultdict(float)
        
        for s in todas_solicitacoes:
            if s.status and s.status.upper() in ['PENDENTE', 'PENDING', 'ORCAMENTO_ENVIADO', 'ORÇAMENTO ENVIADO']:
                total_pendentes += 1
                
            elif s.status and s.status.upper() in ['CONCLUIDO', 'CONCLUÍDO', 'COMPLETED', 'FINALIZADO']:
                total_concluidos += 1
                
                # Limpeza extrema do valor
                valor_db = s.final_price if s.final_price is not None else (s.budget if s.budget is not None else 0)
                valor_bruto = str(valor_db).upper().replace('R$', '').replace(' ', '').replace(',', '.')
                valor_limpo = re.sub(r'[^0-9.]', '', valor_bruto)
                
                if valor_limpo:
                    try:
                        valor_float = float(valor_limpo)
                        total_investido += valor_float
                        
                        # Agrupa gastos por categoria
                        nome_categoria = s.professional.category.name if s.professional and s.professional.category else 'Outros'
                        gastos_por_categoria[nome_categoria] += valor_float
                    except ValueError:
                        pass

        # Prepara listas para o Chart.js
        labels_categorias = list(gastos_por_categoria.keys())
        valores_categorias = list(gastos_por_categoria.values())

        return render_template('dashboard_client.html', 
                               solicitacoes=todas_solicitacoes, 
                               total_pendentes=total_pendentes, 
                               total_concluidos=total_concluidos, 
                               total_investido=total_investido,
                               labels_categorias=labels_categorias,
                               valores_categorias=valores_categorias)


# --------------------------
# GERENCIAMENTO DE PEDIDOS (PROFISSIONAL)
# --------------------------

@app.route('/atualizar-pedido/<int:pedido_id>/<string:novo_status>')
@login_required
def atualizar_status_pedido(pedido_id, novo_status):
    pedido = ServiceRequest.query.get_or_404(pedido_id)
    prof = Professional.query.filter_by(user_id=current_user.id).first()

    # Segurança: Verifica se o pedido realmente pertence ao profissional logado
    if not prof or pedido.professional_id != prof.id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('dashboard'))

    # Atualiza o status
    pedido.status = novo_status
    db.session.commit()

    status_msg = {
        'aceito': 'Pedido aceito com sucesso!',
        'recusado': 'Pedido recusado.',
        'concluido': 'Serviço marcado como concluído!'
    }

    flash(status_msg.get(novo_status, 'Status atualizado!'), 'success')
    return redirect(url_for('dashboard'))


@app.route('/chat/<int:request_id>', methods=['GET', 'POST'])
@login_required
def chat(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    # Segurança: Apenas o cliente ou o profissional do pedido podem acessar o chat
    is_client = current_user.id == service_request.client_id
    prof = Professional.query.filter_by(user_id=current_user.id).first()
    is_prof = prof and prof.id == service_request.professional_id

    if not (is_client or is_prof):
        flash('Acesso negado ao chat.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            # Aplica a censura antes de salvar
            content_seguro = censurar_dados(content)

            new_message = Message(
                request_id=service_request.id,
                sender_id=current_user.id,
                content=content_seguro
            )
            db.session.add(new_message)

            # Notificar a outra parte
            recipient_id = service_request.professional.user_id if is_client else service_request.client_id
            notification_msg = f"Nova mensagem de {current_user.name} no serviço '{service_request.title}'"
            notif = Notification(user_id=recipient_id, message=notification_msg, link=url_for(
                'chat', request_id=service_request.id))
            db.session.add(notif)

            db.session.commit()
        return redirect(url_for('chat', request_id=request_id))

    # Busca mensagens ordenadas por tempo
    messages = Message.query.filter_by(
        request_id=request_id).order_by(Message.timestamp.asc()).all()

    return render_template('chat.html', service_request=service_request, messages=messages)


@app.route('/solicitacao/<int:request_id>/detalhes')
@login_required
def detalhes_solicitacao(request_id):
    solicitacao = ServiceRequest.query.get_or_404(request_id)
    # Garante que apenas o cliente dono ou o profissional possam ver
    if current_user.id not in [solicitacao.client_id, solicitacao.professional.user_id] and getattr(current_user, 'user_type', '') != 'admin':
        flash('Acesso negado.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('detalhes_solicitacao.html', solicitacao=solicitacao)


@app.route('/solicitacao/<int:request_id>/cancelar', methods=['POST'])
@login_required
def cancelar_solicitacao(request_id):
    solicitacao = ServiceRequest.query.get_or_404(request_id)
    
    # Regra de Segurança: Apenas o cliente que criou a solicitação pode cancelá-la
    if solicitacao.client_id != current_user.id:
        flash('Acesso negado. Você não tem permissão para cancelar este pedido.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Regra de Negócio: Não cancelar se já estiver concluído ou cancelado
    if solicitacao.status.lower() in ['concluído', 'concluido', 'completed', 'cancelado', 'cancelled']:
        flash('Este pedido não pode mais ser cancelado.', 'warning')
        return redirect(url_for('detalhes_solicitacao', request_id=solicitacao.id))
        
    try:
        solicitacao.status = 'Cancelado'
        db.session.commit()
        flash('Solicitação cancelada com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erro ao cancelar a solicitação.', 'danger')
        
    return redirect(url_for('detalhes_solicitacao', request_id=solicitacao.id))


@app.route('/enviar-orcamento/<int:request_id>', methods=['POST'])
@login_required
def enviar_orcamento(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)
    prof = Professional.query.filter_by(user_id=current_user.id).first()

    # Validação de segurança: apenas o profissional do pedido pode enviar
    if not prof or prof.id != service_request.professional_id:
        flash('Acesso negado. Apenas o profissional pode enviar o orçamento.', 'danger')
        return redirect(url_for('dashboard'))

    valor = request.form.get('final_price')
    if valor:
        try:
            service_request.final_price = float(valor.replace(',', '.'))
            service_request.status = 'orcamento_enviado'

            # Notificar o cliente
            notif_msg = f"Orçamento final de R$ {service_request.final_price:.2f} recebido no serviço '{service_request.title}'."
            notif = Notification(user_id=service_request.client_id, message=notif_msg, link=url_for(
                'chat', request_id=service_request.id))
            db.session.add(notif)

            db.session.commit()
            flash('Orçamento final enviado com sucesso!', 'success')
        except ValueError:
            flash('Valor numérico inválido.', 'danger')

    return redirect(url_for('chat', request_id=request_id))


@app.route('/responder-orcamento/<int:request_id>', methods=['POST'])
@login_required
def responder_orcamento(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    # Validação de segurança: apenas o cliente do pedido pode responder
    if current_user.id != service_request.client_id:
        flash('Acesso negado. Apenas o cliente pode aceitar o orçamento.', 'danger')
        return redirect(url_for('dashboard'))

    acao = request.form.get('acao')
    if acao == 'aceitar':
        service_request.status = 'aceito'
        flash('Orçamento aceito! O serviço foi fechado.', 'success')
    elif acao == 'recusar':
        service_request.status = 'recusado'
        flash('Orçamento recusado.', 'info')

    db.session.commit()
    return redirect(url_for('chat', request_id=request_id))


@app.route('/cancelar-pedido/<int:request_id>', methods=['POST'])
@login_required
def cancelar_pedido(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    # Trava de Segurança: Apenas o cliente dono pode cancelar
    if current_user.id != service_request.client_id:
        flash('Acesso negado. Apenas o dono do pedido pode cancelá-lo.', 'danger')
        return redirect(url_for('dashboard'))

    # Trava de Status: Não pode cancelar se já foi aceito ou concluído
    if service_request.status in ['aceito', 'concluido']:
        flash(
            'Não é possível cancelar um pedido que já foi aceito ou concluído.', 'warning')
        return redirect(url_for('dashboard'))

    service_request.status = 'CANCELADO'
    db.session.commit()

    flash('Pedido cancelado com sucesso.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/avaliar-servico/<int:request_id>', methods=['GET', 'POST'])
@login_required
def avaliar_servico(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)

    # Segurança: Apenas o cliente do pedido pode avaliar
    if current_user.id != service_request.client_id:
        flash('Acesso negado. Apenas o cliente que solicitou o serviço pode avaliá-lo.', 'danger')
        return redirect(url_for('dashboard'))

    # Regra de Negócio: Apenas serviços concluídos podem ser avaliados
    if service_request.status != 'concluido':
        flash('Apenas serviços marcados como concluídos podem ser avaliados.', 'warning')
        return redirect(url_for('dashboard'))

    # Evita avaliações duplicadas
    existing_review = Review.query.filter_by(request_id=request_id).first()
    if existing_review:
        flash('Este serviço já foi avaliado.', 'info')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        rating = request.form.get('rating')
        comment = (request.form.get('comment') or '').strip()

        # CENSURA OBRIGATÓRIA: Aplicando Regex nos comentários
        comment_seguro = censurar_dados(comment)

        new_review = Review(
            request_id=service_request.id,
            professional_id=service_request.professional_id,
            client_id=current_user.id,
            rating=int(rating) if rating else 5,
            comment=comment_seguro,
            created_at=datetime.utcnow()
        )

        db.session.add(new_review)
        db.session.commit()

        flash('Obrigado pela sua avaliação! Isso ajuda a comunidade.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('review.html', service_request=service_request)


@app.route('/profissional_cancela_pedido/<int:request_id>', methods=['POST'])
@login_required
def profissional_cancela_pedido(request_id):
    service_request = ServiceRequest.query.get_or_404(request_id)
    prof = Professional.query.filter_by(user_id=current_user.id).first()

    # Trava de Segurança: Apenas o profissional designado pode cancelar
    if not prof or prof.id != service_request.professional_id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('dashboard'))

    # Trava de Status: Não pode cancelar se já foi concluído ou já está cancelado
    if service_request.status in ['concluido', 'CANCELADO']:
        flash('Não é possível cancelar um serviço já finalizado ou cancelado.', 'warning')
        return redirect(url_for('dashboard'))

    service_request.status = 'CANCELADO'
    db.session.commit()

    flash('Serviço cancelado/desistido com sucesso.', 'success')
    return redirect(url_for('dashboard'))


# --------------------------
# PERFIL
# --------------------------


@app.route('/perfil')
@login_required
def perfil():

    user = User.query.get_or_404(current_user.id)
    prof = Professional.query.filter_by(user_id=user.id).first()
    return render_template("perfil.html", user=user, prof=prof)


# --------------------------
# solicitar profissional
# --------------------------
@app.route('/profissional_solicitar')
@login_required
def profissional_solicitar():
    user = User.query.get_or_404(current_user.id)
    prof = Professional.query.filter_by(user_id=user.id).first()
    return render_template("professional_solicitar.html", user=user, professional=prof)


# --------------------------
# EXCLUIR PRÓPRIO USUÁRIO
# --------------------------
@app.route('/excluir_proprio_usuario')
@login_required
def excluir_proprio_usuario():
    user = User.query.get(int(current_user.id))
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))

    user_id = user.id

    # Logout antes de apagar
    logout_user()

    # Excluir requests onde ele é cliente
    ServiceRequest.query.filter(ServiceRequest.client_id == user_id).delete(
        synchronize_session=False)

    # Se for profissional, excluir requests onde profissional é o perfil do usuário
    prof = Professional.query.filter_by(user_id=user_id).first()
    if prof:
        ServiceRequest.query.filter(ServiceRequest.professional_id == prof.id).delete(
            synchronize_session=False)
        # excluir reviews relacionadas ao profissional
        Review.query.filter_by(professional_id=prof.id).delete(
            synchronize_session=False)
        # remover perfil profissional
        db.session.delete(prof)

    # excluir reviews onde foi cliente
    Review.query.filter_by(client_id=user_id).delete(synchronize_session=False)

    # excluir usuário
    db.session.delete(user)
    db.session.commit()

    return redirect(url_for('index'))

# --------------------------
# API – validar CEP
# --------------------------


@app.route('/api/validar-cep/<string:cep>')
def api_validate_cep(cep):
    data = validate_cep_garanhuns(cep)
    if data:
        return jsonify(data)
    return jsonify({'error': 'CEP inválido ou fora de Garanhuns–PE'}), 400

# --------------------------
# CATEGORIAS CRUD (PROTEGIDAS PELO ADMIN)
# --------------------------


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    menssagem = None

    if request.method == 'POST':
        login = request.form.get('login')
        senha = request.form.get('password')

        if login == 'admin' and senha == 'senha123':
            session['usuario'] = True
            # Redireciona para a rota do dashboard que criamos abaixo
            return redirect(url_for('admin_dashboard'))
        else:
            menssagem = 'Usuario ou senha incorretos.'
            return render_template('admin/login_admin.html', menssagem=menssagem)

    return render_template('admin/login_admin.html', menssagem=menssagem)


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Puxa os dados reais do seu banco de dados para os 4 cartões informativos
    total_categorias = ServiceCategory.query.count()
    total_profissionais = Professional.query.count()
    total_usuarios = User.query.count()
    total_pedidos = ServiceRequest.query.count()

    # Dados para Gráficos
    pedidos_por_status = db.session.query(
        ServiceRequest.status, func.count(ServiceRequest.id)
    ).group_by(ServiceRequest.status).all()
    
    status_labels = [s[0].upper() for s in pedidos_por_status]
    status_values = [s[1] for s in pedidos_por_status]

    pedidos_por_categoria = db.session.query(
        ServiceCategory.name, func.count(ServiceRequest.id)
    ).join(Professional, Professional.category_id == ServiceCategory.id)\
     .join(ServiceRequest, ServiceRequest.professional_id == Professional.id)\
     .group_by(ServiceCategory.name).all()
    
    cat_labels = [c[0] for c in pedidos_por_categoria]
    cat_values = [c[1] for c in pedidos_por_categoria]

    # Renderiza o arquivo que criamos estendendo a sua base_dashboard.html
    return render_template('admin/dashboard.html',
                           total_categorias=total_categorias,
                           total_profissionais=total_profissionais,
                           total_usuarios=total_usuarios,
                           total_pedidos=total_pedidos,
                           status_labels=status_labels,
                           status_values=status_values,
                           cat_labels=cat_labels,
                           cat_values=cat_values)


@app.route('/logout_admin')
def logout_admin():
    if 'usuario' in session:
        session.pop('usuario', None)
        return redirect(url_for('admin'))
    else:
        return redirect(url_for('admin'))
    



@app.route('/admin/usuarios/listar')
def admin_listar_usuarios():
    # Garantir proteção para que apenas o admin aceda
    if not session.get('usuario'):
        flash('Acesso restrito ao administrador.', 'danger')
        return redirect(url_for('admin'))

    # Procura todos os utilizadores registados no sistema
    usuarios = User.query.order_by(User.name).all()

    return render_template('admin/usuarios/listar.html', usuarios=usuarios)


@app.route('/admin/categorias/listar')
def listar_categorias():
    categorias = ServiceCategory.query.all()
    return render_template('admin/categorias/listar.html', categorias=categorias)


@app.route('/admin/categorias/criar', methods=['GET', 'POST'])
def adicionar_categoria():
    if request.method == 'POST':
        imagem = request.files.get('Imagem')
        imagem_base64 = None

        # Se uma imagem for enviada, converte para base64
        if imagem and imagem.filename != "":
            imagem_base64 = base64.b64encode(imagem.read()).decode('utf-8')

        nome = (request.form.get('name') or '').strip()
        descricao = (request.form.get('description') or '').strip()

        if not nome:
            flash('Nome da categoria é obrigatório.', 'danger')
            return redirect(url_for('adicionar_categoria'))

        if ServiceCategory.query.filter_by(name=nome).first():
            flash('Categoria já existe.', 'danger')
            return redirect(url_for('adicionar_categoria'))

        cat = ServiceCategory(
            name=nome,
            description=descricao,
            created_at=datetime.utcnow()
            # image=imagem_base64  ← se tiver esse campo no seu model
        )

        db.session.add(cat)
        db.session.commit()

        flash('Categoria adicionada com sucesso!', 'success')
        return redirect(url_for('listar_categorias'))

    return render_template('admin/categorias/criar.html')


@app.route('/admin/categorias/editar/<int:id>', methods=['GET', 'POST'])
def editar_categoria(id):
    categoria = db.session.get(ServiceCategory, id)
    if not categoria:
        abort(404)

    if request.method == 'POST':
        imagem = request.files.get('Imagem')

        # Atualiza a imagem somente se uma nova for enviada
        if imagem and imagem.filename != "":
            imagem_base64 = base64.b64encode(imagem.read()).decode('utf-8')
            # categoria.image = imagem_base64  ← se tiver o campo

        categoria.name = (request.form.get('name') or categoria.name).strip()
        categoria.description = (request.form.get(
            'description') or categoria.description).strip()

        db.session.commit()
        flash('Categoria atualizada.', 'success')
        return redirect(url_for('listar_categorias'))

    return render_template('admin/categorias/editar.html', categoria=categoria)


@app.route('/admin/categorias/exluir/<int:id>', methods=['POST'])
def deletar_categoria(id):
    categoria = db.session.get(ServiceCategory, id)
    if not categoria:
        abort(404)
    # evita exclusão se houver profissionais vinculados
    try:
        has_profs = (categoria.professionals is not None) and (
            len(categoria.professionals) > 0)
    except Exception:
        # caso relationship seja dynamic ou outro tipo, tente count
        try:
            has_profs = categoria.professionals.count() > 0
        except Exception:
            has_profs = False

    if has_profs:
        flash('Não é possível remover: existem profissionais vinculados a essa categoria.', 'danger')
        return redirect(url_for('listar_categorias'))
    db.session.delete(categoria)
    db.session.commit()
    flash('Categoria removida.', 'success')
    return redirect(url_for('listar_categorias'))


@app.route('/admin/solicitacoes')
def admin_listar_solicitacoes():
    # Garante segurança para que apenas o administrador logado acesse
    if not session.get('usuario'):
        return redirect(url_for('admin'))
        
    # Busca todas as solicitações ordenando pelas mais recentes
    # Nota: Adapte o nome do modelo (ex: ServiceRequest ou Solicitacao) conforme o seu banco
    solicitacoes = ServiceRequest.query.order_by(ServiceRequest.id.desc()).all()
    
    return render_template('admin/solicitacoes/listar.html', solicitacoes=solicitacoes)
# --------------------------
# PROFISSÕES CRUD
# --------------------------


@app.route('/admin/profissoes')
def listar_profissoes():
    # Garante que apenas o admin acessa a listagem geral
    if not session.get('usuario'):
        return redirect(url_for('admin'))
        
    # Busca todos os profissionais trazendo junto os usuários e categorias vinculados (Evita o bug de lista vazia)
    profs = Professional.query.order_by(Professional.id.desc()).all()
    return render_template('admin/profissoes/listar.html', profissionais=profs)


@app.route('/admin/profissoes/criar', methods=['GET', 'POST'])
def adicionar_profissao():
    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()
    if request.method == 'POST':
        try:
            category_id = int(request.form.get('category_id')) if request.form.get('category_id') else None
        except ValueError:
            category_id = None
            
        prof = Professional(
            user_id=current_user.id,
            category_id=category_id,
            bio=censurar_dados((request.form.get('bio') or '').strip()),
            experience_years=int(request.form.get('experience_years')) if request.form.get('experience_years') else None,
            starting_price=float(request.form.get('starting_price')) if request.form.get('starting_price') else None,
            response_time=request.form.get('response_time') or '24 horas',
            created_at=datetime.utcnow()
        )
        db.session.add(prof)
        db.session.commit()
        flash('Perfil profissional criado!', 'success')
        return redirect(url_for('admin_dashboard')) # Redireciona para o seu novo dashboard admin
        
    return render_template('admin/profissoes/criar.html', categories=categories)


@app.route('/admin/profissoes/editar/<int:id>', methods=['GET', 'POST'])
def editar_profissao(id):
    prof = db.session.get(Professional, id)
    if not prof:
        abort(404)
    
    # Permite que o próprio usuário OU o Administrador edite o perfil
    if prof.user_id != current_user.id and not session.get('usuario'):
        flash('Acesso negado.', 'danger')
        return redirect(url_for('admin_dashboard'))
        
    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()
    if request.method == 'POST':
        prof.category_id = int(request.form.get('category_id')) if request.form.get('category_id') else None
        prof.bio = censurar_dados((request.form.get('bio') or prof.bio).strip())
        prof.experience_years = int(request.form.get('experience_years')) if request.form.get('experience_years') else None
        prof.starting_price = float(request.form.get('starting_price')) if request.form.get('starting_price') else None
        prof.response_time = request.form.get('response_time') or prof.response_time
        
        db.session.commit()
        flash('Perfil atualizado.', 'success')
        return redirect(url_for('listar_profissoes'))
        
    return render_template('admin/profissoes/editar.html', prof=prof, categories=categories)


@app.route('/admin/profissoes/excluir/<int:id>', methods=['POST'])
def deletar_profissao(id):
    prof = db.session.get(Professional, id)
    if not prof:
        abort(404)
    
    # Permite que o próprio usuário OU o Administrador delete o perfil
    if prof.user_id != current_user.id and not session.get('usuario'):
        flash('Acesso negado.', 'danger')
        return redirect(url_for('listar_profissoes'))
        
    # Remove reviews associados ao profissional para não quebrar a integridade do banco
    Review.query.filter_by(professional_id=prof.id).delete(synchronize_session=False)
    
    db.session.delete(prof)
    db.session.commit()
    flash('Perfil profissional excluído.', 'success')
    # CORRIGIDO: Agora redireciona usando o nome correto da função Python
    return redirect(url_for('listar_profissoes'))

# --------------------------
# EDITAR PERFIL DO USUÁRIO
# --------------------------


@app.route('/usuarios/perfil/editar', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    user = db.session.get(User, current_user.id)
    prof = Professional.query.filter_by(user_id=user.id).first()
    categories = ServiceCategory.query.order_by(ServiceCategory.name).all()

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'profile_info':
            user.name = (request.form.get('name') or user.name).strip()
            user.email = (request.form.get('email') or user.email).strip().lower()
            user.phone = (request.form.get('phone') or user.phone).strip()
            user.cep = (request.form.get('cep') or user.cep).strip()
            user.address = (request.form.get('address') or user.address).strip()
            user.neighborhood = (request.form.get('neighborhood') or user.neighborhood).strip()
            user.city = (request.form.get('city') or user.city).strip()
            user.state = (request.form.get('state') or user.state).strip().upper()

            # Upload de Foto de Perfil
            foto = request.files.get('profile_photo')
            if foto and foto.filename:
                filename = secure_filename(foto.filename)
                novo_nome = f"user_{current_user.id}_{filename}"
                caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], novo_nome)
                foto.save(caminho_salvar)
                user.profile_image = novo_nome

            # Se for profissional, atualizar dados do perfil profissional também
            if prof:
                prof.category_id = int(request.form.get('category_id')) if request.form.get('category_id') else None
                prof.experience_years = int(request.form.get('experience_years') or 0)
                prof.starting_price = float(request.form.get('starting_price') or 0)
                prof.response_time = request.form.get('response_time')
                prof.bio = censurar_dados((request.form.get('bio') or '').strip())
                prof.tags = censurar_dados((request.form.get('tags') or '').strip())
                prof.availability = request.form.get('availability')
                prof.service_range = request.form.get('service_range')
                
                # Processamento do Portfólio (Múltiplas Fotos)
                arquivos_portfolio = request.files.getlist('portfolio_photos')
                
                fotos_atuais = prof.get_portfolio_photos()
                novas_fotos_salvas = []
                
                import uuid
                for file in arquivos_portfolio:
                    if file and file.filename != '':
                        filename = secure_filename(file.filename)
                        novo_nome = f"portf_{current_user.id}_{uuid.uuid4().hex[:8]}_{filename}"
                        caminho_salvar = os.path.join(app.config['UPLOAD_FOLDER'], novo_nome)
                        file.save(caminho_salvar)
                        novas_fotos_salvas.append(novo_nome)
                
                todas_fotos = (fotos_atuais + novas_fotos_salvas)[:6]
                if todas_fotos or len(todas_fotos) == 0:
                    import json
                    prof.portfolio_photos = json.dumps(todas_fotos)

            db.session.commit()
            flash('Perfil atualizado com sucesso!', 'success')

        elif form_type == 'security':
            from werkzeug.security import check_password_hash
            current_pass = request.form.get('current_password')
            new_pass = request.form.get('new_password')
            confirm_pass = request.form.get('confirm_password')

            if not check_password_hash(user.password_hash, current_pass):
                flash('Senha atual incorreta.', 'danger')
            elif new_pass != confirm_pass:
                flash('A nova senha e a confirmação não coincidem.', 'danger')
            elif len(new_pass) < 6:
                flash('A nova senha deve ter pelo menos 6 caracteres.', 'warning')
            else:
                user.password_hash = generate_password_hash(new_pass)
                db.session.commit()
                flash('Senha alterada com sucesso!', 'success')

        return redirect(url_for('editar_perfil'))

    return render_template('usuarios/editar.html', user=user, prof=prof, categories=categories)


@app.route('/remover-foto-portfolio/<int:photo_index>', methods=['POST'])
@login_required
def remover_foto_portfolio(photo_index):
    prof = Professional.query.filter_by(user_id=current_user.id).first()
    if not prof:
        abort(403)

    current_portfolio = prof.get_portfolio_photos()
    if 0 <= photo_index < len(current_portfolio):
        current_portfolio.pop(photo_index)
        prof.portfolio_photos = json.dumps(current_portfolio)
        db.session.commit()
        flash('Foto removida do portfólio.', 'success')

    return redirect(url_for('editar_perfil'))


# --------------------------
# PÁGINAS INSTITUCIONAIS
# --------------------------
@app.route('/quem-somos')
def quem_somos():
    return render_template('pages/quem_somos.html')

@app.route('/como-funciona')
def como_funciona():
    return render_template('pages/como_funciona.html')

@app.route('/contato')
def contato():
    return render_template('pages/contato.html')

@app.route('/ajuda')
def ajuda():
    return render_template('pages/ajuda.html')

@app.route('/termos')
def termos():
    return render_template('pages/termos.html')

@app.route('/privacidade')
def privacidade():
    return render_template('pages/privacidade.html')


# --------------------------
# API – Chat Polling
# --------------------------
@app.route('/api/chat/<int:solicitacao_id>/mensagens')
@login_required
def get_chat_messages(solicitacao_id):
    # Verifique se o usuário tem permissão (é o cliente ou o profissional do pedido)
    solicitacao = ServiceRequest.query.get_or_404(solicitacao_id)
    if current_user.id not in [solicitacao.client_id, solicitacao.professional.user_id]:
        return jsonify({'error': 'Acesso negado'}), 403

    # Busca as mensagens
    mensagens = Message.query.filter_by(request_id=solicitacao_id).order_by(Message.timestamp.asc()).all()
    
    chat_data = []
    for m in mensagens:
        chat_data.append({
            'id': m.id,
            'remetente_id': m.sender_id,
            'remetente_nome': m.sender.name if m.sender else '',
            'texto': m.content,
            'data': m.timestamp.strftime('%H:%M') if m.timestamp else ''
        })
        
    return jsonify({'mensagens': chat_data, 'meu_id': current_user.id})


# --------------------------
# UTILITÁRIOS (startup)
# --------------------------


# --------------------------
# execução
# --------------------------
if __name__ == '__main__':
    # Cria tabelas se necessário
    with app.app_context():
        db.create_all()
        # Opcional: criar admin se definir variáveis de ambiente DEFAULT_ADMIN_EMAIL/PASSWORD
        # create_app_admin_if_missing()

    app.run(debug=True)

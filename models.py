from database import db
from flask_login import UserMixin
from datetime import datetime
import json


# =====================================================
# USER
# =====================================================
class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))

    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), default='client')  # client / professional

    # Endereço
    cep = db.Column(db.String(9))
    address = db.Column(db.String(200))
    neighborhood = db.Column(db.String(120))
    city = db.Column(db.String(120))
    state = db.Column(db.String(2))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    professional_profile = db.relationship(
        "Professional",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    client_requests = db.relationship(
        "ServiceRequest",
        backref="client",
        foreign_keys="ServiceRequest.client_id",
        cascade="all, delete-orphan"
    )

    reviews_given = db.relationship(
        "Review",
        backref="client",
        foreign_keys="Review.client_id",
        cascade="all, delete-orphan"
    )

    notifications = db.relationship(
        "Notification",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"


# =====================================================
# SERVICE CATEGORY
# =====================================================
class ServiceCategory(db.Model):
    __tablename__ = "service_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    image = db.Column(db.Text)  # <-- FALTAVA! AGORA A IMAGEM É SALVA AQUI

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    professionals = db.relationship(
        "Professional",
        backref="category",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Category {self.name}>"



# =====================================================
# PROFESSIONAL
# =====================================================
class Professional(db.Model):
    __tablename__ = "professionals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("service_categories.id"))

    bio = db.Column(db.Text)
    experience_years = db.Column(db.Integer)
    starting_price = db.Column(db.Float)

    # NOVAS FUNCIONALIDADES
    profile_photo = db.Column(db.String(255))            
    portfolio_photos = db.Column(db.Text)                # JSON
    services_offered = db.Column(db.Text)                # JSON
    tags = db.Column(db.String(255))                     
    availability = db.Column(db.String(255))             

    verified = db.Column(db.Boolean, default=False)
    response_time = db.Column(db.String(50), default="24 horas (estimado)")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    service_requests = db.relationship(
        "ServiceRequest",
        backref="professional",
        cascade="all, delete-orphan"
    )

    reviews = db.relationship(
        "Review",
        backref="professional",
        cascade="all, delete-orphan"
    )

    # Helpers JSON
    def get_portfolio_photos(self):
        try:
            return json.loads(self.portfolio_photos or "[]")
        except:
            return []

    def get_services(self):
        try:
            return json.loads(self.services_offered or "[]")
        except:
            return []

    # Propriedades úteis
    @property
    def average_rating(self):
        if not self.reviews or len(self.reviews) == 0:
            return 0.0
        try:
            total = sum(r.rating for r in self.reviews if r.rating is not None)
            count = len([r for r in self.reviews if r.rating is not None])
            return total / count if count > 0 else 0.0
        except:
            return 0.0

    @property
    def review_count(self):
        return len(self.reviews)

    def __repr__(self):
        return f"<Professional {self.id} - User {self.user_id}>"


# =====================================================
# SERVICE REQUEST
# =====================================================
class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    professional_id = db.Column(db.Integer, db.ForeignKey("professionals.id"), nullable=False)

    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    budget = db.Column(db.Float)
    final_price = db.Column(db.Float)
    preferred_date = db.Column(db.String(100))

    status = db.Column(db.String(40), default="pendente")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    review = db.relationship(
        "Review",
        backref="service_request",
        uselist=False,
        cascade="all, delete-orphan"
    )

    messages = db.relationship(
        "Message",
        backref="request",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Request {self.id} - {self.status}>"


# =====================================================
# MESSAGE (CHAT)
# =====================================================
class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("service_requests.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamento para acessar o remetente
    sender = db.relationship("User", backref="messages_sent")

    def __repr__(self):
        return f"<Message {self.id} from User {self.sender_id}>"


# =====================================================
# REVIEW
# =====================================================
class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)

    request_id = db.Column(db.Integer, db.ForeignKey("service_requests.id"), nullable=False)
    professional_id = db.Column(db.Integer, db.ForeignKey("professionals.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Review {self.id} rating={self.rating}>"


# =====================================================
# NOTIFICATION
# =====================================================
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Notification {self.id} for User {self.user_id} read={self.is_read}>"

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

# Configurações JWT
SECRET_KEY = "raizes-nordeste-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Configuração do banco SQLite
DATABASE_URL = "sqlite:///./raizes.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Criptografia de senha
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Modelos do banco
class UsuarioDB(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    email = Column(String, unique=True)
    senha = Column(String)
    role = Column(String, default="CLIENTE")

class ProdutoDB(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    preco = Column(Float)
    disponivel = Column(Boolean, default=True)
    sazonal = Column(Boolean, default=False)

class ClienteDB(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    email = Column(String, unique=True)
    consentimento_lgpd = Column(Boolean, default=False)

class UnidadeDB(Base):
    __tablename__ = "unidades"
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String)
    cidade = Column(String)
    ativa = Column(Boolean, default=True)

class EstoqueDB(Base):
    __tablename__ = "estoques"
    id = Column(Integer, primary_key=True, index=True)
    unidade_id = Column(Integer, ForeignKey("unidades.id"))
    produto_id = Column(Integer, ForeignKey("produtos.id"))
    quantidade = Column(Integer, default=0)

class PedidoDB(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    unidade_id = Column(Integer, ForeignKey("unidades.id"))
    canal = Column(String)
    status = Column(String, default="AGUARDANDO_PAGAMENTO")
    total = Column(Float, default=0.0)
    itens = relationship("ItemPedidoDB", back_populates="pedido")

class ItemPedidoDB(Base):
    __tablename__ = "itens_pedido"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"))
    produto_id = Column(Integer)
    quantidade = Column(Integer)
    pedido = relationship("PedidoDB", back_populates="itens")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Raízes do Nordeste API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Funções JWT
def verificar_senha(senha, hash):
    return pwd_context.verify(senha, hash)

def hash_senha(senha):
    return pwd_context.hash(senha)

def criar_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_usuario_atual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == email).first()
    if usuario is None:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return usuario

# Schemas
class UsuarioSchema(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = "CLIENTE"

class UnidadeSchema(BaseModel):
    nome: str
    cidade: str
    ativa: bool = True

class EstoqueSchema(BaseModel):
    unidade_id: int
    produto_id: int
    quantidade: int

class ProdutoSchema(BaseModel):
    nome: str
    preco: float
    disponivel: bool = True
    sazonal: bool = False

class ClienteSchema(BaseModel):
    nome: str
    email: str
    consentimento_lgpd: bool

class ItemPedidoSchema(BaseModel):
    produto_id: int
    quantidade: int

class PedidoSchema(BaseModel):
    cliente_id: int
    unidade_id: int
    canal: str
    itens: List[ItemPedidoSchema]

# Endpoints Auth
@app.post("/auth/registro", tags=["Auth"])
def registrar(usuario: UsuarioSchema, db: Session = Depends(get_db)):
    existente = db.query(UsuarioDB).filter(UsuarioDB.email == usuario.email).first()
    if existente:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    db_usuario = UsuarioDB(
        nome=usuario.nome,
        email=usuario.email,
        senha=hash_senha(usuario.senha),
        role=usuario.role
    )
    db.add(db_usuario)
    db.commit()
    return {"mensagem": "Usuário registrado com sucesso"}

@app.post("/auth/login", tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == form.username).first()
    if not usuario or not verificar_senha(form.password, usuario.senha):
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")
    token = criar_token({"sub": usuario.email, "role": usuario.role})
    return {"access_token": token, "token_type": "bearer"}

# Endpoints Unidades
@app.get("/unidades", tags=["Unidades"])
def listar_unidades(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return db.query(UnidadeDB).all()

@app.post("/unidades", tags=["Unidades"])
def criar_unidade(unidade: UnidadeSchema, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    db_unidade = UnidadeDB(**unidade.dict())
    db.add(db_unidade)
    db.commit()
    db.refresh(db_unidade)
    return {"mensagem": "Unidade criada com sucesso", "unidade": db_unidade}

# Endpoints Estoque
@app.get("/estoques", tags=["Estoque"])
def listar_estoques(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return db.query(EstoqueDB).all()

@app.post("/estoques", tags=["Estoque"])
def criar_estoque(estoque: EstoqueSchema, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    db_estoque = EstoqueDB(**estoque.dict())
    db.add(db_estoque)
    db.commit()
    db.refresh(db_estoque)
    return {"mensagem": "Estoque criado com sucesso", "estoque": db_estoque}

@app.get("/estoques/unidade/{unidade_id}", tags=["Estoque"])
def estoque_por_unidade(unidade_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    estoques = db.query(EstoqueDB).filter(EstoqueDB.unidade_id == unidade_id).all()
    if not estoques:
        raise HTTPException(status_code=404, detail="Nenhum estoque encontrado para esta unidade")
    return estoques

# Endpoints Produtos (protegidos)
@app.get("/produtos", tags=["Produtos"])
def listar_produtos(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return db.query(ProdutoDB).all()

@app.post("/produtos", tags=["Produtos"])
def criar_produto(produto: ProdutoSchema, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    db_produto = ProdutoDB(**produto.dict())
    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)
    return {"mensagem": "Produto criado com sucesso", "produto": db_produto}

# Endpoints Clientes (protegidos)
@app.get("/clientes", tags=["Clientes"])
def listar_clientes(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return db.query(ClienteDB).all()

@app.post("/clientes", tags=["Clientes"])
def criar_cliente(cliente: ClienteSchema, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    if not cliente.consentimento_lgpd:
        raise HTTPException(status_code=400, detail="Cliente precisa dar consentimento LGPD")
    db_cliente = ClienteDB(**cliente.dict())
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return {"mensagem": "Cliente criado com sucesso", "cliente": db_cliente}

# Endpoints Pedidos (protegidos)
@app.get("/pedidos", tags=["Pedidos"])
def listar_pedidos(db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return db.query(PedidoDB).all()

@app.get("/pedidos/{pedido_id}", tags=["Pedidos"])
def buscar_pedido(pedido_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return pedido

@app.post("/pedidos", tags=["Pedidos"])
def criar_pedido(pedido: PedidoSchema, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    cliente = db.query(ClienteDB).filter(ClienteDB.id == pedido.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    canais_validos = ["APP", "TOTEM", "BALCAO", "PICKUP"]
    if pedido.canal not in canais_validos:
        raise HTTPException(status_code=400, detail=f"Canal inválido. Use: {canais_validos}")
    total = 0.0
    for item in pedido.itens:
        produto = db.query(ProdutoDB).filter(ProdutoDB.id == item.produto_id).first()
        if not produto:
            raise HTTPException(status_code=404, detail=f"Produto {item.produto_id} não encontrado")
        if not produto.disponivel:
            raise HTTPException(status_code=400, detail=f"Produto {produto.nome} não disponível")

        # Valida estoque por unidade
        estoque = db.query(EstoqueDB).filter(
            EstoqueDB.unidade_id == pedido.unidade_id,
            EstoqueDB.produto_id == item.produto_id
        ).first()
        if not estoque or estoque.quantidade < item.quantidade:
            raise HTTPException(status_code=409,
                                detail=f"Estoque insuficiente para o produto {produto.nome} na unidade")

        total += produto.preco * item.quantidade
    db_pedido = PedidoDB(
        cliente_id=pedido.cliente_id,
        unidade_id=pedido.unidade_id,
        canal=pedido.canal,
        status="AGUARDANDO_PAGAMENTO",
        total=total
    )
    db.add(db_pedido)
    db.commit()
    db.refresh(db_pedido)
    for item in pedido.itens:
        db_item = ItemPedidoDB(
            pedido_id=db_pedido.id,
            produto_id=item.produto_id,
            quantidade=item.quantidade
        )
        db.add(db_item)
    db.commit()
    return {"mensagem": "Pedido criado com sucesso", "pedido_id": db_pedido.id, "total": total, "status": db_pedido.status}

@app.post("/pedidos/{pedido_id}/pagamento", tags=["Pedidos"])
def processar_pagamento(pedido_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.status != "AGUARDANDO_PAGAMENTO":
        raise HTTPException(status_code=409, detail="Pedido não está aguardando pagamento")
    if pedido.total <= 1000:
        pedido.status = "PAGAMENTO_APROVADO"
        mensagem = "Pagamento aprovado!"
    else:
        pedido.status = "CANCELADO"
        mensagem = "Pagamento recusado - valor acima do limite"
    db.commit()
    return {"mensagem": mensagem, "total": pedido.total, "status": pedido.status}
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# Configuração do banco SQLite
DATABASE_URL = "sqlite:///./raizes.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelos do banco de dados
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

class PedidoDB(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    unidade = Column(String)
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

# Cria as tabelas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Raízes do Nordeste API")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schemas Pydantic
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
    unidade: str
    canal: str
    itens: List[ItemPedidoSchema]

# Endpoints Produtos
@app.get("/produtos", tags=["Produtos"])
def listar_produtos(db: Session = Depends(get_db)):
    return db.query(ProdutoDB).all()

@app.post("/produtos", tags=["Produtos"])
def criar_produto(produto: ProdutoSchema, db: Session = Depends(get_db)):
    db_produto = ProdutoDB(**produto.dict())
    db.add(db_produto)
    db.commit()
    db.refresh(db_produto)
    return {"mensagem": "Produto criado com sucesso", "produto": db_produto}

# Endpoints Clientes
@app.get("/clientes", tags=["Clientes"])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(ClienteDB).all()

@app.post("/clientes", tags=["Clientes"])
def criar_cliente(cliente: ClienteSchema, db: Session = Depends(get_db)):
    if not cliente.consentimento_lgpd:
        raise HTTPException(status_code=400, detail="Cliente precisa dar consentimento LGPD")
    db_cliente = ClienteDB(**cliente.dict())
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return {"mensagem": "Cliente criado com sucesso", "cliente": db_cliente}

# Endpoints Pedidos
@app.get("/pedidos", tags=["Pedidos"])
def listar_pedidos(db: Session = Depends(get_db)):
    return db.query(PedidoDB).all()

@app.get("/pedidos/{pedido_id}", tags=["Pedidos"])
def buscar_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return pedido

@app.post("/pedidos", tags=["Pedidos"])
def criar_pedido(pedido: PedidoSchema, db: Session = Depends(get_db)):
    # Valida cliente
    cliente = db.query(ClienteDB).filter(ClienteDB.id == pedido.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Valida canal
    canais_validos = ["APP", "TOTEM", "BALCAO", "PICKUP"]
    if pedido.canal not in canais_validos:
        raise HTTPException(status_code=400, detail=f"Canal inválido. Use: {canais_validos}")

    # Calcula total
    total = 0.0
    for item in pedido.itens:
        produto = db.query(ProdutoDB).filter(ProdutoDB.id == item.produto_id).first()
        if not produto:
            raise HTTPException(status_code=404, detail=f"Produto {item.produto_id} não encontrado")
        if not produto.disponivel:
            raise HTTPException(status_code=400, detail=f"Produto {produto.nome} não disponível")
        total += produto.preco * item.quantidade

    # Cria pedido
    db_pedido = PedidoDB(
        cliente_id=pedido.cliente_id,
        unidade=pedido.unidade,
        canal=pedido.canal,
        status="AGUARDANDO_PAGAMENTO",
        total=total
    )
    db.add(db_pedido)
    db.commit()
    db.refresh(db_pedido)

    # Cria itens
    for item in pedido.itens:
        db_item = ItemPedidoDB(
            pedido_id=db_pedido.id,
            produto_id=item.produto_id,
            quantidade=item.quantidade
        )
        db.add(db_item)
    db.commit()

    return {"mensagem": "Pedido criado com sucesso", "pedido_id": db_pedido.id, "total": total, "status": db_pedido.status}

# Endpoint Pagamento
@app.post("/pedidos/{pedido_id}/pagamento", tags=["Pedidos"])
def processar_pagamento(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.status != "AGUARDANDO_PAGAMENTO":
        raise HTTPException(status_code=409, detail="Pedido não está aguardando pagamento")

    # Gateway mock
    if pedido.total <= 1000:
        pedido.status = "PAGAMENTO_APROVADO"
        mensagem = "Pagamento aprovado!"
    else:
        pedido.status = "CANCELADO"
        mensagem = "Pagamento recusado - valor acima do limite"

    db.commit()
    return {"mensagem": mensagem, "total": pedido.total, "status": pedido.status}
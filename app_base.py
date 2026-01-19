import os 
from dotenv import load_dotenv
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
import aiomysql
import json
import ssl

load_dotenv()
ssl_ctx = ssl.create_default_context()

# ---------------------------
# CONEXÃO COM MYSQL
# ---------------------------

async def inicializar_banco():
    conn = await aiomysql.connect(
        host=str(os.getenv("serverless-europe-west2.sysp0000.db2.skysql.com")),
        port=int(os.getenv("4036")),
        user=os.getenv("dbpgf28848341"),
        password=os.getenv("jZ6F~gwQIbHeknUeZxJZV"),
        autocommit=True,
        ssl=ssl_ctx 
    )
    cursor = await conn.cursor()

    await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {os.getenv('DB_NAME')}") 
    await cursor.execute(f"USE {os.getenv('DB_NAME')}")

    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            produto JSON NOT NULL,
            quantidade INT NOT NULL,
            valor DECIMAL(10,2) NOT NULL,
            adicionais JSON,
            status VARCHAR(20) DEFAULT 'Pendente'
        ) AUTO_INCREMENT = 100000
    """)

    await cursor.close()
    conn.close()
## END


async def get_conn():
    return await aiomysql.connect(
        host=os.getenv("SQL_HOSTNAME"),
        port=int(os.getenv("SQL_PORT")),
        user=os.getenv("SQL_USER"),
        password=os.getenv("SQL_PASSWORD"),
        db=os.getenv("SQL_DBNAME"),   # <- agora o banco já existe
        autocommit=True,
        ssl=ssl_ctx  # MariaDB Cloud exige SSL
    )
## END


@asynccontextmanager
async def app_startup(app: FastAPI):
    # Aqui entra o código que rodaria no startup
    print("Inicializando banco...")
    await inicializar_banco()
    yield
    # Aqui entra o código que rodaria no shutdown (opcional)
## END


app = FastAPI(
    title="Lanchonete do Bairro",
    summary="Aplicação de registro de pedidos da lanchonete",
    lifespan=app_startup
)

# ---------------------------
# MODELO DE DADOS
# ---------------------------

class Pedido(BaseModel):
    id: Optional[int] = None
    nome: str
    produto: list[str]
    quantidade: int
    valor: float
    adicionais: Optional[list[str]] = None
    status: str = "Pendente"
## END


# ---------------------------
# POST - Criar pedido
# ---------------------------

@app.post("/pedidos")
async def cria_pedido(pedido: Pedido):

    conn = await get_conn()
    cursor = await conn.cursor()

    sql = """
        INSERT INTO pedidos (nome, produto, quantidade, valor, adicionais, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """

    await cursor.execute(sql, (
        pedido.nome,
        json.dumps(pedido.produto),       
        pedido.quantidade,
        pedido.valor,
        json.dumps(pedido.adicionais),    
        pedido.status
    ))

    await cursor.execute("SELECT LAST_INSERT_ID()")
    pedido_id = (await cursor.fetchone())[0]

    pedido.id = pedido_id

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(pedido)
    )
## END

# ---------------------------
# GET - Listar pedidos
# ---------------------------

@app.get("/pedidos")
async def retorna_pedidos():

    conn = await get_conn()
    cursor = await conn.cursor(aiomysql.DictCursor)

    await cursor.execute("SELECT * FROM pedidos")
    resultados = await cursor.fetchall()

    for r in resultados:
        r["produto"] = json.loads(r["produto"]) if r["produto"] else []
        r["adicionais"] = json.loads(r["adicionais"]) if r["adicionais"] else []

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(resultados)
    )
## END

@app.get("/pedidos/{id}")
async def retorna_pedido(id: int):

    conn = await get_conn()
    cursor = await conn.cursor(aiomysql.DictCursor)

    await cursor.execute("SELECT * FROM pedidos WHERE id = %s", (id,))
    pedido = await cursor.fetchone()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    # converter JSON para lista Python
    pedido["produto"] = json.loads(pedido["produto"])
    pedido["adicionais"] = json.loads(pedido["adicionais"]) if pedido["adicionais"] else []

    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(pedido)
    )
## END

@app.put("/pedidos/{id}")
async def atualiza_pedido(id: int, pedido_atualizado: Pedido):

    conn = await get_conn()
    cursor = await conn.cursor()

    # Verificar se existe
    await cursor.execute("SELECT id FROM pedidos WHERE id = %s", (id,))
    existe = await cursor.fetchone()

    if not existe:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    sql = """
        UPDATE pedidos
        SET nome = %s,
            produto = %s,
            quantidade = %s,
            valor = %s,
            adicionais = %s,
            status = %s
        WHERE id = %s
    """

    await cursor.execute(sql, (
        pedido_atualizado.nome,
        json.dumps(pedido_atualizado.produto),
        pedido_atualizado.quantidade,
        pedido_atualizado.valor,
        json.dumps(pedido_atualizado.adicionais),
        pedido_atualizado.status,
        id
    ))

    pedido_atualizado.id = id

    return JSONResponse(
        status_code=200,
        content={
            "msg": "Pedido atualizado com sucesso!",
            "pedido": jsonable_encoder(pedido_atualizado)
        }
    )
## END

@app.patch("/pedidos/{id}")
async def atualiza_status(id: int, status_pedido: dict):

    conn = await get_conn()
    cursor = await conn.cursor()

    # Verificar se existe
    await cursor.execute("SELECT id FROM pedidos WHERE id = %s", (id,))
    existe = await cursor.fetchone()

    if not existe:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    await cursor.execute(
        "UPDATE pedidos SET status = %s WHERE id = %s",
        (status_pedido["status"], id)
    )

    return JSONResponse(
        status_code=200,
        content={"msg": "Status atualizado com sucesso!"}
    )
## END

@app.delete("/pedidos/{id}")
async def remover_pedido(id: int):

    conn = await get_conn()
    cursor = await conn.cursor(aiomysql.DictCursor)

    # Buscar antes para retornar ao usuário
    await cursor.execute("SELECT * FROM pedidos WHERE id = %s", (id,))
    pedido = await cursor.fetchone()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    await cursor.execute("DELETE FROM pedidos WHERE id = %s", (id,))

    pedido["produto"] = json.loads(pedido["produto"])
    pedido["adicionais"] = json.loads(pedido["adicionais"]) if pedido["adicionais"] else []

    return JSONResponse(
        status_code=200,
        content={
            "msg": "Pedido removido com sucesso",
            "pedido": jsonable_encoder(pedido)
        }
    )
## END
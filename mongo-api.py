from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True
)

client = MongoClient(os.environ["MONGO_URI"])
db = client["ISIS2304D10202610"]

@app.get("/")
def inicio():
    return {"estado": "API funcionando correctamente"}

# RF4 -> consultar reseñas de un hotel
@app.get('/api/hoteles/{hotel}/reviews')
def get_reviews(hotel: str):
    reviews = list(
        db["reviews"].find(
            {"hotel.nombre": hotel},
            {"_id": 0}
        )
    )
    return reviews

# RF6 -> historial de reseñas propias
@app.get('/api/clientes/{nombre}/reviews')
def get_reviews_cliente(nombre: str):
    reviews = list(
        db["reviews"].find(
            {"cliente.nombre": nombre},
            {"_id": 0}
        )
    )
    return reviews

# RF1 -> crear reseña
@app.post('/api/hoteles/{hotel}/reviews')
def post_review(hotel: str, datos: dict):
    existe = db["reviews"].find_one({
        "idReserva": datos["idReserva"]
    })
    if existe:
        return {
            "error": "La reserva ya tiene reseña"
        }
    datos["hotel"] = {
        "nombre": hotel
    }
    datos["fechaCreacion"] = datetime.now().isoformat()
    datos["estado"] = "publicada"
    datos["utiles"] = 0
    datos["destacada"] = False
    db["reviews"].insert_one(datos)
    return {
        "mensaje": "Review guardada"
    }

# RF2 -> editar reseña
@app.put('/api/reviews/{id_reserva}')
def editar_review(id_reserva: str, datos: dict):
    db["reviews"].update_one(
        {"idReserva": id_reserva},
        {
            "$set": {
                "comentario": datos["comentario"],
                "calificacion": datos["calificacion"]
            }
        }
    )
    return {
        "mensaje": "Review actualizada"
    }

# RF3 -> eliminar reseña (soft delete)
@app.delete('/api/reviews/{id_reserva}')
def eliminar_review(id_reserva: str):
    db["reviews"].update_one(
        {"idReserva": id_reserva},
        {
            "$set": {
                "estado": "eliminada"
            }
        }
    )
    return {
        "mensaje": "Review eliminada"
    }

# RF5 -> marcar útil
@app.put('/api/reviews/{id_reserva}/util')
def marcar_util(id_reserva: str):
    db["reviews"].update_one(
        {"idReserva": id_reserva},
        {
            "$inc": {
                "utiles": 1
            }
        }
    )
    return {
        "mensaje": "Voto registrado"
    }

# RF7 -> responder reseña
@app.put('/api/reviews/{id_reserva}/respuesta')
def responder_review(id_reserva: str, datos: dict):
    db["reviews"].update_one(
        {"idReserva": id_reserva},
        {
            "$set": {
                "respuestaAdmin": {
                    "administrador": datos["administrador"],
                    "respuesta": datos["respuesta"],
                    "fecha": datetime.now().isoformat()
                }
            }
        }
    )
    return {
        "mensaje": "Respuesta guardada"
    }

# RF9 -> destacar reseña
@app.put('/api/reviews/{id_reserva}/destacar')
def destacar_review(id_reserva: str):
    review = db["reviews"].find_one({"idReserva": id_reserva})
    if review:
        db["reviews"].update_many(
            {"hotel.nombre": review["hotel"]["nombre"]},
            {"$set": {"destacada": 0}}
        )
    db["reviews"].update_one(
        {"idReserva": id_reserva},
        {"$set": {"destacada": 1}}
    )
    return {"mensaje": "Reseña destacada"}

# RFC1 -> Top 10 hoteles por calificación promedio
@app.get('/api/hoteles/top')
def top_hoteles():
    pipeline = [
        {
            "$group": {
                "_id": "$hotel.nombre",
                "promedio": {"$avg": "$calificacion"},
                "total_reviews": {"$sum": 1}
            }
        },
        {
            "$sort": {"promedio": -1}
        },
        {
            "$limit": 10
        }
    ]
    resultado = list(db["reviews"].aggregate(pipeline))
    return [
        {
            "hotel": r["_id"],
            "promedio": round(r["promedio"], 1),
            "total_reviews": r["total_reviews"]
        }
        for r in resultado
    ]

# RFC2 -> Evolución de reputación de un hotel mes a mes
@app.get('/api/hoteles/{hotel}/evolucion')
def evolucion_hotel(hotel: str, anio: int):
    pipeline = [
        {
            "$match": {
                "hotel.nombre": hotel,
                "fechaCreacion": {
                    "$regex": f"^{anio}"
                }
            }
        },
        {
            "$group": {
                "_id": {"$substr": ["$fechaCreacion", 0, 7]},
                "promedio": {"$avg": "$calificacion"},
                "total": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id": 1}
        }
    ]
    resultado = list(db["reviews"].aggregate(pipeline))
    return [
        {
            "mes": r["_id"],
            "promedio": round(r["promedio"], 1),
            "total": r["total"]
        }
        for r in resultado
    ]

# RFC3 -> Perfil comparativo de hoteles por ciudad
@app.get('/api/ciudades/{ciudad}/hoteles')
def comparativo_ciudad(ciudad: str):
    pipeline = [
        {
            "$match": {
                "hotel.ciudad": ciudad
            }
        },
        {
            "$group": {
                "_id": "$hotel.nombre",
                "promedio": {"$avg": "$calificacion"},
                "total": {"$sum": 1},
                "con_respuesta": {
                    "$sum": {
                        "$cond": [{"$ifNull": ["$respuestaAdmin", False]}, 1, 0]
                    }
                },
                "destacadas": {
                    "$sum": {
                        "$cond": [{"$eq": ["$destacada", 1]}, 1, 0]
                    }
                }
            }
        },
        {
            "$sort": {"promedio": -1}
        }
    ]
    resultado = list(db["reviews"].aggregate(pipeline))

    if not resultado:
        return []

    promedio_ciudad = round(
        sum(r["promedio"] for r in resultado) / len(resultado), 1
    )

    return [
        {
            "hotel": r["_id"],
            "promedio": round(r["promedio"], 1),
            "total_reviews": r["total"],
            "pct_con_respuesta": round((r["con_respuesta"] / r["total"]) * 100, 1),
            "pct_destacadas": round((r["destacadas"] / r["total"]) * 100, 1),
            "bajo_promedio": round(r["promedio"], 1) < promedio_ciudad,
            "promedio_ciudad": promedio_ciudad
        }
        for r in resultado
    ]


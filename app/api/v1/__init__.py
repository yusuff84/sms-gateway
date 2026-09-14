from fastapi import APIRouter
from app.api.v1.sms import router as sms_router
from app.api.v1.devices import router as devices_router

api_v1_router = APIRouter()
api_v1_router.include_router(sms_router)
api_v1_router.include_router(devices_router)

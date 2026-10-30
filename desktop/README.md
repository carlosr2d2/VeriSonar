# Cliente de escritorio Windows

VeriSonar Desktop envuelve el frontend Next.js con Electron para desplegar un instalador NSIS.

```bash
# 1. Levantar el stack
docker compose up -d frontend backend

# 2. Cliente
cd desktop
npm install
npm start
```

Empaquetado:

```bash
npm run pack:win
```

El ejecutable habla con la API en `http://localhost:8000` a través del proxy de Next.js. En call centers se puede apuntar `VERISONAR_URL` a un origen interno.

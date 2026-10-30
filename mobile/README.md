# API móvil VeriSonar (React Native)

Contrato estable bajo `/api/mobile/v1` (espejo de `/api/v1`) para no romper clientes cuando el web evolucione.

## Autenticación

`POST /api/mobile/v1/auth/login` (OAuth2 password)

`POST /api/mobile/v1/auth/push-token`

```json
{ "token": "<fcm-or-apns>", "platform": "android" }
```

Plataformas: `android` | `ios` | `web` | `windows`.

## Análisis

`POST /api/mobile/v1/analyze` multipart:

- `file` audio
- `title`
- `language` (`es` ahora, `en` en fase posterior)
- `context` opcional

`GET /api/mobile/v1/analyze/{audio_id}`

## Informes

`GET /api/mobile/v1/reports`

`GET /api/mobile/v1/reports/{id}`

`GET /api/mobile/v1/reports/{id}/pdf`

`GET /api/mobile/v1/reports/{id}/json`

## Tiempo real (fase 2)

`wss://{host}/ws/analyze/{session_id}?token={jwt}`

Notificaciones push: el worker llama a FCM cuando `PUSH_ENABLED=true` y el usuario registró token.

## Esqueleto RN

```ts
const BASE = "https://verisonar.local/api/mobile/v1";

export async function enqueueAudio(token: string, file: { uri: string; name: string; type: string }) {
  const body = new FormData();
  body.append("file", file as any);
  body.append("title", "Entrevista móvil");
  body.append("language", "es");
  return fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
}
```

No se incluye el binario de React Native en este repositorio: el backend ya expone el contrato versionado y los tokens push.

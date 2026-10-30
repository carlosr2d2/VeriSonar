# Audios de ejemplo para VeriSonar

No son pruebas de mentira ni exámenes VSA comerciales. Sirven para probar STT, acústica y el léxico ES-LATAM sin usar material con derechos ni grabaciones forenses.

## Listos para subir (carpeta `data/samples`)

| Archivo | Duración | Origen | Licencia | Para qué |
|---|---|---|---|---|
| `10_entrevista_vsa_directa.wav` | ~1 min 14 s | TTS Helena + Sabina, guion propio | voz de sistema | Preguntas/respuestas sí-no, respuestas fluidas |
| `11_entrevista_vsa_atenuada.wav` | ~1 min 31 s | TTS Helena + Sabina, guion propio | voz de sistema | Mismas preguntas; hedging, «te juro», «no recuerdo» |
| `12_entrevista_herrera_uy.wav` | ~1 min 41 s | [Radio El Espectador, 1958](https://commons.wikimedia.org/wiki/File:Entrevista_a_Luis_Alberto_de_Herrera_en_radio_El_Espectador.ogg) | dominio público (UY) | Entrevista radiofónica real, rioplatense |
| `13_entrevista_nadia_heck.wav` | ~1 min 28 s | [Juan Manuel Dotta](https://commons.wikimedia.org/wiki/File:Audio_entrevista_Nadia_Heck.wav) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Entrevista breve, voz humana |
| `14_entrevista_aimaretti.wav` | ~4 min 40 s | [Norambrosino / Origlia](https://commons.wikimedia.org/wiki/File:Entrevista_al_Ing._Agronomo_Gabriel_Aimaretti.ogg) | CC BY-SA 4.0 | Preguntas y respuestas sobre el agro |
| `15_entrevista_urrutia.wav` | ~1 min 19 s | [NaBUru38](https://commons.wikimedia.org/wiki/File:Entrevista_a_Santiago_Urrutia_del_4_de_noviembre_de_2017.ogg) | CC BY-SA 4.0 | Entrevista al aire libre (ruido de fondo) |
| `16_entrevista_mujeres_mx.wav` | 3 min (recorte) | [Melorca, Chihuahua](https://commons.wikimedia.org/wiki/File:Mujeres_en_mi_region.ogg) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Podcast Q&A, es-MX |
| `08_mx_relato_fluido.wav` | ~19 s | TTS Microsoft Sabina (es-MX) | voz de sistema, texto propio | Relato en primera persona, pocas muletillas |
| `09_mx_relato_atenuado.wav` | ~25 s | TTS Microsoft Sabina (es-MX) | voz de sistema, texto propio | Hedging, «te juro», «o sea», «no recuerdo» |
| `07_argentina_clima_concat.wav` | ~16 s | [OpenSLR 61](https://openslr.org/61/) clima AR | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Voz humana rioplatense, habla leída |
| `01`–`03` argentina clima | ~5 s c/u | OpenSLR 61 | CC BY-SA 4.0 | Clips cortos AR |
| `04`–`05` españa clima | ~5 s c/u | OpenSLR 61 | CC BY-SA 4.0 | Contraste peninsular |
| `06_wikipedia_es_hablada.wav` | ~2 min 32 s | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Es-Brfxxccxxmnpcccclllmmnprxvclmnckssqlbb11116-article.ogg) | CC (artículo hablado) | Pista larga para STT/acústica |

**Empiece por `10` y `11` (entrevista) o `08` y `09` (relato):** el motor lingüístico debería puntuar más riesgo en la versión atenuada. Eso no significa que la voz “mienta”; es un texto actuado.

Los clips `12`–`16` son entrevistas humanas con licencia libre. No son interrogatorios ni pruebas de estrés de voz.

Guion de `10`/`11`: `data/samples/raw/entrevista_vsa_guion.txt`.

## Fuentes en internet (para bajar más)

1. **OpenSLR — español latinoamericano (WAV, CC BY-SA 4.0)**  
   Crowdsourcing de Google para TTS, voces voluntarias anónimas:  
   - Argentina [SLR61](https://openslr.org/61/)  
   - Chile [SLR71](https://openslr.org/71/)  
   - Colombia [SLR72](https://openslr.org/72/)  
   - Perú [SLR73](https://openslr.org/73/)  
   - Puerto Rico [SLR74](https://openslr.org/74/)  
   El paquete de mensajes del clima (33 MB) ya se usó aquí:  
   `https://www.openslr.org/resources/61/es_weather_messages.zip`

2. **Mozilla Common Voice español (MP3, CC0)**  
   [Scripted Speech](https://mozilladatacollective.com/datasets/cmqim2spa00synr071fcp7av0) y [habla espontánea](https://mozilladatacollective.com/datasets/cmqi28y2v004imf076oh7e5zs) (~28 MB).  
   Condición de uso: no identificar a los hablantes.

3. **LibriVox / Internet Archive (MP3, dominio público)**  
   Lecturas voluntarias. Útil para acento mexicano: *El Periquillo Sarniento*.  
   https://librivox.org/el-periquillo-sarniento-i-y-ii-by-jose-gutierrez/  
   https://archive.org/details/periquillosarnientoiyii_2406_librivox  
   (Archive.org a veces responde 503; reintente o use el catálogo de LibriVox.)

4. **Wikimedia Commons — entrevistas**  
   [Audio files of interviews](https://commons.wikimedia.org/wiki/Category:Audio_files_of_interviews) y [audio en español](https://commons.wikimedia.org/wiki/Category:Audio_files_in_Spanish).  
   De ahí salieron `12`–`16`.

Los exámenes VSA/CVSA de fabricantes (NITV, etc.) y el corpus CSC Deceptive Speech (LDC2013S09) **no son de uso libre**. No hay packs legales de “entrevista VSA real” para bajar.

## Qué no usar

Noticieros, interrogatorios, llamadas reales ni clips de YouTube con copyright. VeriSonar no está pensado para “cazar mentirosos” en audio ajeno.

## Cómo probarlos

1. Entre a http://localhost:3000  
2. **Nuevo análisis** → complete la ficha y elija `10_entrevista_vsa_directa.wav` y luego `11_entrevista_vsa_atenuada.wav`  
3. Compare transcripción (turnos pregunta/respuesta), línea base de control y puntaje VSA por ítem  
4. Opcional: suba `14` (más larga) o `16` (es-MX humana) para estrés de STT

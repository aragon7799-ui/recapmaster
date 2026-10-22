# RecapMaster AI

RecapMaster AI သည် အမှန်တကယ် video file များကို ingest လုပ်ပြီး မြန်မာဘာသာ recap MP4 များ ထုတ်ပေးသော post-production workbench ဖြစ်သည်။ UI တွင် ပြထားသော progress သည် backend job event များမှသာလာပြီး FFprobe ဖြင့် မစစ်ဆေးရသေးသောဖိုင်ကို verified output အဖြစ် မပြပါ။

## Local setup

Node.js 22၊ pnpm 9.15.9၊ Python 3.12၊ FFmpeg နှင့် FFprobe လိုအပ်ပါသည်။ ပထမဆုံး dependency များ install လုပ်ပါ။

```bash
pnpm install
python3 -m pip install -r requirements.txt
```

`.env.example` ကို `.env` အဖြစ် copy လုပ်ပါ။ Manus managed Cloud/Preview တွင် `MANUS_API_URL`၊ `MANUS_API_KEY` နှင့် `DATABASE_URL` သည် runtime မှ ပေးထားလျှင် ထပ်ထည့်စရာမလိုပါ။ Local run အတွက် Burmese-capable LLM အတွက် `OPENAI_API_BASE`/`OPENAI_API_KEY` သို့မဟုတ် Manus credentials တစ်စုံလိုအပ်ပါသည်။ Faster-whisper သည် model ကို ပထမဆုံးအသုံးပြုချိန်တွင် download လုပ်နိုင်သောကြောင့် network နှင့် disk space လိုအပ်ပါသည်။ Edge-TTS သည် voice service သို့ network ချိတ်ဆက်ရပါမည်။

```bash
cp .env.example .env
pnpm dev
```

Frontend သည် `http://localhost:3000` နှင့် FastAPI သည် `http://localhost:8000` တွင် run မည်။ Frontend ၏ `/api/*` requests များကို development rewrite ဖြင့် FastAPI သို့ ပို့သည်။ Health စစ်ရန် `curl http://localhost:8000/health` ကိုသုံးပါ။

## Real pipeline

Job တစ်ခုစတင်လျှင် source ကို တကယ် download/upload လုပ်ပြီး FFprobe ဖြင့် စစ်သည်။ Audio ကို faster-whisper ဖြင့် transcribe လုပ်ရန်ကြိုးစားပြီး managed Whisper surface ကို real fallback အဖြစ်သုံးနိုင်သည်။ PySceneDetect သည် scene cut timestamps ထုတ်ပေးသည်။ LLM သည် analysis၊ Burmese Unicode recap script၊ social metadata နှင့် thumbnail suggestion ကိုရေးသည်။ Edge-TTS သည် `my-MM-ThihaNeural` သို့မဟုတ် `my-MM-NilarNeural` ဖြင့် narration ထုတ်သည်။ FFmpeg သည် clip cut၊ SRT subtitle burn-in၊ logo overlay၊ generated/configured royalty-free bed၊ loudness normalization၊ master composition နှင့် selected platform re-render များကို တကယ်လုပ်သည်။

No music file is silently copied from an unknown source. `ROYALTY_FREE_MUSIC_PATH` သတ်မှတ်ထားလျှင် ထိုဖိုင်ကိုသုံးပြီး မသတ်မှတ်ထားလျှင် pipeline သည် low-volume tonal bed တစ်ခုကို FFmpeg ဖြင့် generate လုပ်သည်။ This generated bed is not a commercial song and avoids a hidden copyright claim. All render artifacts are FFprobe-verified before download.

## Platform and quality behavior

YouTube Standard၊ YouTube Shorts၊ TikTok၊ Facebook Reels၊ Facebook Feed၊ Instagram Reels၊ Instagram Feed၊ Instagram Story၊ X/Twitter၊ Threads၊ Telegram နှင့် Generic 4:5 ကို တစ်ပြိုင်တည်းရွေးနိုင်သည်။ Render တစ်ခုချင်းစီသည် သီးခြား MP4 ဖြစ်ပြီး center crop/pad-safe conversion၊ subtitle safe placement၊ logo safe placement နှင့် deterministic filename ရှိသည်။ Draft/480p၊ Standard/720p၊ High/1080p၊ Ultra/2K နှင့် Cinema/4K options ရှိသည်။ UI estimate သည် source duration နှင့် selected bitrate ကို အခြေခံသော estimate သာဖြစ်ပြီး final size သည် FFprobe မှဖတ်ထားသော တန်ဖိုးဖြစ်သည်။

## API outline

- `POST /api/projects` — multipart URL သို့မဟုတ် video upload နှင့် optional logo
- `POST /api/jobs` — real job စတင်ရန် options
- `GET /api/jobs/:id` — job state, event log, artifacts, FFprobe metadata
- `GET /api/jobs/:id/events` — SSE progress stream
- `GET /api/artifacts/:id/download` — verified file download
- `GET /api/history` — durable project history
- `GET /health` — unauthenticated readiness

## Honest failure behavior

YouTube block၊ unsupported direct URL၊ missing credentials၊ faster-whisper/model failure၊ Edge-TTS voice failure၊ FFmpeg stderr၊ missing subtitle filter၊ storage failure နှင့် platform-specific render failure များသည် real error အဖြစ် UI တွင် ပြပါမည်။ Platform တစ်ခု fail ဖြစ်လျှင် အခြား verified platform output များကို မဖျက်ဘဲ `completed_with_errors` အဖြစ် ပြပါမည်။ Published container filesystem သည် durable မဟုတ်သောကြောင့် production တွင် object storage integration ကို configure လုပ်ရန်လိုပြီး local download endpoint သည် local artifact ရှိနေသရွေ့သာ အလုပ်လုပ်မည်။

## Production build

```bash
NEXT_OUTPUT=export pnpm --filter frontend build
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 3000
```

Dockerfile သည် Node၊ Python၊ FFmpeg၊ frontend static export နှင့် FastAPI တစ်ခုတည်းသော listener image ကို တည်ဆောက်ပေးသည်။ Container health path သည် `/health` ဖြစ်သည်။ Secrets များကို Git ထဲမထည့်ပါနှင့်။

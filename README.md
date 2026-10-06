# ZigZag PA Alert (gratis, tanpa laptop)

Script Python + GitHub Actions yang cek pola harmonik (port dari Pine "ZigZag PA Strategy V4.1")
tiap jam, lalu kirim notif ke Telegram.

## Setup (sekali saja)
1. **Bikin bot Telegram**: chat @BotFather -> `/newbot` -> simpan **token**.
2. **Ambil chat id**: kirim pesan apa saja ke bot kamu, lalu buka
   `https://api.telegram.org/bot<TOKEN>/getUpdates` -> cari `"chat":{"id": ...}`.
3. **Bikin repo GitHub** (boleh private), upload semua isi folder ini
   (pastikan folder `.github/workflows/zigzag.yml` ikut ke-upload).
4. Repo -> **Settings -> Secrets and variables -> Actions**:
   - Secrets: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
   - (opsional) Variables: `SYMBOLS` = daftar simbol Yahoo dipisah koma, default `GC=F` (emas)
5. Tab **Actions** -> "ZigZag PA Alert" -> **Run workflow** -> centang `test` untuk tes Telegram.
   Lalu jalankan sekali lagi tanpa centang untuk tes normal.

## Catatan
- Simbol Yahoo: emas `GC=F` (futures), `XAUUSD=X` kadang kosong; forex contoh `EURUSD=X`, `GBPUSD=X`.
- Data Yahoo bisa sedikit beda dari broker MT5 -> pivot/level bisa geser sedikit. Pakai sebagai alert.
- Notif dikirim sekali per pivot per arah (state disimpan di `state.json`).
- Jadwal GitHub kadang telat beberapa menit. Kalau repo tidak ada aktivitas 60 hari, jadwal bisa
  dimatikan GitHub; tinggal aktifkan lagi dari tab Actions.
- Parameter lain (env): `INTERVAL`, `USE_HA`, `EW_RATE`, `TP_RATE`, `SL_RATE`, `TZ_OFFSET`.

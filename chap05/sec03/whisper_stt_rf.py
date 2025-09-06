# -*- coding: utf-8 -*-
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Tuple, Optional

import torch
import pandas as pd
from transformers import pipeline
from pyannote.audio import Pipeline as PyannotePipeline


# -----------------------------
# 환경 설정
# -----------------------------
# ffmpeg 경로 (필요 시 수정)
FFMPEG_BIN = r"D:\ffmpeg-2025-09-01-git-3ea6c2fe25-full_build\bin"
if FFMPEG_BIN and Path(FFMPEG_BIN).exists():
    os.environ["PATH"] += os.pathsep + FFMPEG_BIN

# pyannote diarization용 HF 토큰 (반드시 본인 토큰으로 교체)
HF_TOKEN = "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"

# 경고(정보성) 숨김: torchaudio backend deprecation
warnings.filterwarnings("ignore", category=UserWarning, module=r"pyannote\.audio\.core\.io")


# -----------------------------
# 유틸
# -----------------------------
def now() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}")
    sys.stdout.flush()


# -----------------------------
# ASR (Whisper)
# -----------------------------
def build_asr_pipeline(force_ko: bool = True):
    """GPU 사용 가능 여부에 따라 적절한 모델/정밀도를 선택해 ASR 파이프라인 생성."""
    use_cuda = torch.cuda.is_available()
    device = 0 if use_cuda else "cpu"
    dtype = torch.float16 if use_cuda else torch.float32

    # CPU에서는 큰 모델 금지(매우 느림) → small 권장
    model_id = "openai/whisper-large-v3-turbo" if use_cuda else "openai/whisper-small"

    log(f"[ASR] device={'cuda' if use_cuda else 'cpu'}, dtype={dtype}, model={model_id}")

    generate_kwargs = {"task": "transcribe", "language": "ko"} if force_ko else None

    asr = pipeline(
        task="automatic-speech-recognition",
        model=model_id,
        device=device,
        dtype=dtype,
        return_timestamps=True,
        # whisper에서 chunking은 실험적 → 너무 짧/길지 않게
        chunk_length_s=15,
        stride_length_s=5,
        batch_size=8 if use_cuda else 1,
        generate_kwargs=generate_kwargs,
    )
    return asr


def whisper_to_dataframe(result: dict) -> pd.DataFrame:
    """transformers ASR 결과를 [start, end, text] DataFrame으로 변환."""
    rows = []
    for ch in result.get("chunks", []):
        ts = ch.get("timestamp")
        if not ts or ts[0] is None or ts[1] is None:
            continue
        rows.append([float(ts[0]), float(ts[1]), ch.get("text", "").strip()])
    df = pd.DataFrame(rows, columns=["start", "end", "text"])
    return df


def whisper_stt(audio_file_path: str, output_file_path: str) -> Tuple[dict, pd.DataFrame]:
    """오디오 파일 STT 수행 → CSV 저장."""
    t0 = time.time()
    audio_path = Path(audio_file_path).resolve()
    out_path = Path(output_file_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    asr = build_asr_pipeline(force_ko=True)
    log("[ASR] 추론 시작")
    result = asr(str(audio_path))
    log("[ASR] 추론 완료")

    df = whisper_to_dataframe(result)
    df.to_csv(out_path, index=False, sep="|", encoding="utf-8")
    log(f"[ASR] CSV 저장: {out_path} (rows={len(df)})")
    log(f"[ASR] 소요: {time.time() - t0:.1f}s")
    return result, df


# -----------------------------
# Diarization (pyannote)
# -----------------------------
def diarize_to_rttm(
    audio_file_path: str,
    output_rttm_file_path: str,
    hf_token: Optional[str] = HF_TOKEN,
) -> None:
    """오디오 화자 분리 → RTTM 파일로 저장."""
    t0 = time.time()
    audio_path = Path(audio_file_path).resolve()
    rttm_path = Path(output_rttm_file_path).resolve()
    rttm_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    log("[DIA] 모델 로딩")
    diarizer = PyannotePipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )

    if torch.cuda.is_available():
        diarizer.to(torch.device("cuda"))
        log("[DIA] cuda is available")
    else:
        log("[DIA] cuda is NOT available (CPU는 매우 느릴 수 있습니다)")

    log("[DIA] 추론 시작")
    diarization = diarizer(str(audio_path))
    log("[DIA] 추론 완료")

    with open(rttm_path, "w", encoding="utf-8") as f:
        diarization.write_rttm(f)
    log(f"[DIA] RTTM 저장: {rttm_path} (소요: {time.time() - t0:.1f}s)")


def parse_rttm_to_grouped_csv(rttm_file_path: str, output_csv_file_path: str) -> pd.DataFrame:
    """
    RTTM → DataFrame → speaker 구간 그룹화 → CSV 저장.
    RTTM은 공백이 여러 칸일 수 있으므로 정규식 구분자를 사용.
    """
    rttm_path = Path(rttm_file_path).resolve()
    out_csv = Path(output_csv_file_path).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if not rttm_path.exists():
        raise FileNotFoundError(f"RTTM 파일을 찾을 수 없습니다: {rttm_path}")

    df_rttm = pd.read_csv(
        rttm_path,
        sep=r"\s+",
        engine="python",
        header=None,
        names=["type", "file", "chnl", "start", "duration", "C1", "C2", "speaker_id", "C3", "C4"],
        comment=";",
        skip_blank_lines=True,
    )
    # 숫자 컬럼 안전 변환
    df_rttm["start"] = pd.to_numeric(df_rttm["start"], errors="coerce")
    df_rttm["duration"] = pd.to_numeric(df_rttm["duration"], errors="coerce")
    df_rttm = df_rttm.dropna(subset=["start", "duration"]).copy()
    df_rttm["end"] = df_rttm["start"] + df_rttm["duration"]

    # 연속 동일 화자 구간을 하나의 number로 묶기
    df_rttm["number"] = 0
    for i in range(1, len(df_rttm)):
        if df_rttm.at[i, "speaker_id"] != df_rttm.at[i - 1, "speaker_id"]:
            df_rttm.at[i, "number"] = df_rttm.at[i - 1, "number"] + 1
        else:
            df_rttm.at[i, "number"] = df_rttm.at[i - 1, "number"]

    df_grouped = df_rttm.groupby("number", as_index=False).agg(
        start=("start", "min"),
        end=("end", "max"),
        speaker_id=("speaker_id", "first"),
    )
    df_grouped["duration"] = df_grouped["end"] - df_grouped["start"]

    df_grouped.to_csv(out_csv, index=False, encoding="utf-8")
    log(f"[DIA] 그룹 CSV 저장: {out_csv} (rows={len(df_grouped)})")
    return df_grouped


# -----------------------------
# STT 결과를 Diarization 구간에 매핑
# -----------------------------
def align_stt_to_rttm(df_stt: pd.DataFrame, df_rttm: pd.DataFrame) -> pd.DataFrame:
    """
    STT 청크를 diarization 구간에 최대 겹침(overlap) 기준으로 할당.
    """
    if df_stt is None or df_stt.empty:
        log("[ALIGN] STT 결과가 비어 있습니다. (텍스트 매핑 없이 diarization만 반환)")
        df_rttm["text"] = ""
        return df_rttm

    if df_rttm is None or df_rttm.empty:
        log("[ALIGN] RTTM 결과가 비어 있습니다. (정렬 불가)")
        df = df_rttm.copy() if df_rttm is not None else pd.DataFrame(columns=["start", "end", "speaker_id", "duration", "text"])
        if "text" not in df.columns:
            df["text"] = ""
        return df

    df = df_rttm.copy()
    if "text" not in df.columns:
        df["text"] = ""

    for _, row_stt in df_stt.iterrows():
        s_start, s_end, s_text = row_stt["start"], row_stt["end"], row_stt["text"]

        # 각 diarization 구간과의 overlap 계산
        overlaps = (df[["start", "end"]]
                    .apply(lambda r: max(0.0, min(s_end, r["end"]) - max(s_start, r["start"])), axis=1))
        max_idx = overlaps.idxmax()
        max_val = overlaps[max_idx] if pd.notna(max_idx) else 0.0

        if max_val > 0:
            df.at[max_idx, "text"] += (s_text + "\n")

    return df


# -----------------------------
# 오케스트레이션
# -----------------------------
def stt_to_rttm(
    audio_file_path: str,
    stt_output_file_path: str,
    rttm_file_path: str,
    rttm_csv_file_path: str,
    final_output_csv_file_path: str,
) -> pd.DataFrame:
    """
    1) STT → CSV
    2) Diarization → RTTM → 그룹 CSV
    3) STT 텍스트를 화자 구간에 정렬하여 최종 CSV 저장
    """
    # 1) STT
    _, df_stt = whisper_stt(audio_file_path, stt_output_file_path)

    # 2) Diarization
    diarize_to_rttm(audio_file_path, rttm_file_path, HF_TOKEN)
    df_rttm = parse_rttm_to_grouped_csv(rttm_file_path, rttm_csv_file_path)

    # 3) Align
    log("[ALIGN] STT → RTTM 매핑 시작")
    df_final = align_stt_to_rttm(df_stt, df_rttm)

    out_path = Path(final_output_csv_file_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(out_path, index=False, sep="|", encoding="utf-8")
    log(f"[FINAL] 최종 CSV 저장: {out_path} (rows={len(df_final)})")
    return df_final


# -----------------------------
# main
# -----------------------------
if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    audio_file_path = str(base.parent / "audio" / "싼기타_비싼기타.mp3")             # 원본 오디오
    stt_output_file_path = str(base.parent / "audio" / "싼기타_비싼기타.csv")       # STT 결과
    rttm_file_path = str(base.parent / "audio" / "싼기타_비싼기타.rttm")            # diarization RTTM
    rttm_csv_file_path = str(base.parent / "audio" / "싼기타_비싼기타_rttm.csv")    # diarization 그룹 CSV
    final_csv_file_path = str(base.parent / "audio" / "싼기타_비싼기타_final.csv")  # 최종 결과

    log("[MAIN] 파이프라인 시작")
    try:
        df_final = stt_to_rttm(
            audio_file_path,
            stt_output_file_path,
            rttm_file_path,
            rttm_csv_file_path,
            final_csv_file_path,
        )
        log("[MAIN] 완료")
        print(df_final.head())
    except Exception as e:
        log(f"[ERROR] {type(e).__name__}: {e}")
        raise

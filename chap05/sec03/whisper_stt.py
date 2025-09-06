import os
import torch
import pandas as pd
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from pyannote.audio import Pipeline

os.environ["PATH"] += os.pathsep + r"D:\ffmpeg-2025-09-01-git-3ea6c2fe25-full_build\bin"

def whisper_stt(
        audio_file_path:str,
        output_file_path:str = "./output.csv"
):
    try:
        device="cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        model_id = "openai/whisper-large-v3-turbo"

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
        )
        model.to(device)
        
        processor = AutoProcessor.from_pretrained(model_id)

        pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=device,
            return_timestamps=True,
            chunk_length_s=10,
            stride_length_s=2,
        )

        result=pipe(audio_file_path)
        df=whisper_to_dataframe(result,output_file_path)

        return result,df
    
    except Exception as e:
        print(f"whisper_stt 함수에서 오류가 발생했습니다: {e}")
        return None,None

def whisper_to_dataframe(result,output_file_path):
    start_end_text=[]

    for chunk in result["chunks"]:
        start = chunk["timestamp"][0]
        end=chunk["timestamp"][1]
        text=chunk["text"].strip()
        start_end_text.append([start,end,text])
        
    df=pd.DataFrame(start_end_text,columns=["start","end","text"])
    df.to_csv(output_file_path,index=False,sep="|")
        
    return df

def speaker_diarization(
        audio_file_path:str,
        output_rttm_file_path:str,
        output_csv_file_path:str
    ):
    try:
        print("1. pyannote 파이프라인 로드 시작...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token="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"
        )
        print("2. 파이프라인 로드 완료.")

        if torch.cuda.is_available():
            print('3. CUDA가 사용 가능합니다. GPU로 파이프라인 이동 중...')
            pipeline.to(torch.device("cuda"))
            print('4. 파이프라인 GPU 이동 완료.')
        else:
            print('3. CUDA가 사용 불가능합니다. CPU로 파이프라인 실행 중...')
        
        print(f"5. 화자 분리 시작: {audio_file_path}")
        diarization_pipeline=pipeline(audio_file_path)
        print("6. 화자 분리 완료.")
        
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
        return None
    
    # 이 아래 코드는 오류가 발생하지 않았을 때만 실행됩니다.
    with open(output_rttm_file_path,"w",encoding='utf-8') as rttm:
        diarization_pipeline.write_rttm(rttm)

    df_rttm=pd.read_csv(
        output_rttm_file_path,
        sep=' ',
        header=None,
        names=['type','file','chnl','start','duration','C1','C2','speaker_id','C3','C4']
    )
    df_rttm['end']=df_rttm['start'] + df_rttm['duration']

    df_rttm["number"]=None
    df_rttm.at[0,"number"]=0

    for i in range(1,len(df_rttm)):
        if df_rttm.at[i,"speaker_id"] != df_rttm.at[i-1,"speaker_id"]:
            df_rttm.at[i,"number"] = df_rttm.at[i-1,"number"] + 1
        else:
            df_rttm.at[i,"number"] = df_rttm.at[i-1,"number"]

    df_rttm_grouped = df_rttm.groupby("number").agg(
        start=pd.NamedAgg(column='start',aggfunc='min'),
        end=pd.NamedAgg(column='end',aggfunc='max'),
        speaker_id=pd.NamedAgg(column='speaker_id',aggfunc='first')
    )

    df_rttm_grouped["duration"]=df_rttm_grouped["end"]-df_rttm_grouped["start"]

    df_rttm_grouped.to_csv(
        output_csv_file_path,
        index=False,
        encoding='utf-8'
    )
    return df_rttm_grouped

def stt_to_rttm(
        audio_file_path: str,
        stt_output_file_path: str,
        rttm_file_path: str,
        rttm_csv_file_path: str,
        final_output_csv_file_path: str
    ):

    result,df_stt=whisper_stt(
        audio_file_path,
        stt_output_file_path
    )

    df_rttm=speaker_diarization(
        audio_file_path,
        rttm_file_path,
        rttm_csv_file_path
    )

    df_rttm["text"]=""

    for i_stt, row_stt in df_stt.iterrows():
        overlap_dict={}
        for i_rttm, row_rttm in df_rttm.iterrows():
            overlap=max(0,min(row_stt["end"],row_rttm["end"])-max(row_stt["start"],row_rttm["start"]))
            overlap_dict[i_rttm]=overlap
        
        if overlap_dict:
            max_overlap=max(overlap_dict.values())
            max_overlap_idx=max(overlap_dict, key=overlap_dict.get)
        else:
            max_overlap=0
            max_overlap_idx=None

        if max_overlap > 0 :
            df_rttm.at[max_overlap_idx,"text"] += row_stt["text"] + "\n"

    df_rttm.to_csv(
        final_output_csv_file_path,
        index=False,
        sep='|',
        encoding='utf-8'
    )
    return df_rttm


if __name__ == "__main__":
    audio_file_path="../audio/싼기타_비싼기타.mp3"  # 원본 오디오 파일
    stt_output_file_path="../audio/싼기타_비싼기타.csv" # STT 결과 파일
    rttm_file_path="../audio/싼기타_비싼기타.rttm"   # 화자 분리 원본 파일
    rttm_csv_file_path="../audio/싼기타_비싼기타_rttm.csv"   # 화자 분리 CSV 파일
    final_csv_file_path="../audio/싼기타_비싼기타_final.csv"

    # 이 부분을 주석 처리하거나 삭제합니다.
    # result,df=whisper_stt(
    #     audio_file_path,
    #     stt_output_file_path
    # )

    # if df is not None:
    #     print("whisper_stt 결과:")
    #     print(df)
    # else:
    #     print("데이터프레임 생성에 실패했습니다. 오류 메시지를 확인하세요.")

    # 이 부분을 활성화하여 speaker_diarization 함수만 실행합니다.
    df_rttm = speaker_diarization(
        audio_file_path,
        rttm_file_path,
        rttm_csv_file_path
    )

    if df_rttm is not None:
        print("speaker_diarization 결과:")
        print(df_rttm)
    else:
        print("화자 분리 데이터프레임 생성에 실패했습니다. 오류 메시지를 확인하세요.")
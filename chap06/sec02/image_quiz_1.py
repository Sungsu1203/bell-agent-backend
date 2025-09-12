from glob import glob
import json
from openai import OpenAI
from dotenv import load_dotenv
import os
import base64

load_dotenv(r"D:\GPT_AGENT_2025_BOOK\.env")
api_key=os.getenv('OPENAI_API_KEY')
client =OpenAI(api_key=api_key)

def encode_image(image_path):
    with open(image_path,"rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
    

def image_quiz(image_path, n_trial=0, max_trial=3):
    if n_trial >= max_trial: # 최대 회수에 도달하면 포기
        raise Exception("Failed to generate a quiz")
    
    base64_image=encode_image(image_path) # 이미지를 base64로 인코딩

    quiz_prompt = """
    제공된 이미지를 바탕으로, 다음과 같은 양식으로 퀴즈를 만들어주세요. 
    정답은 1~4 중 하나만 해당하도록 출제하세요.
    토익 리스닝 문제 스타일로 문제를 만들어 주세요.
    아래는 예시입니다. 
    ----- 예시 -----

    Q: 다음 이미지에 대한 설명 중 옳지 않은 것은 무엇인가요?
    - (1) 베이커리에서 사람들이 빵을 사고 있는 모습이 담겨 있습니다.
    - (2) 맨 앞에 서 있는 사람은 빨간색 셔츠를 입고 있습니다.
    - (3) 기차를 타기 위해 줄을 서 있는 사람들이 있습니다.
    - (4) 점원은 노란색 티셔츠를 입고 있습니다.

    Listening: Which of the following descriptions of the image is incorrect?
    - (1) It shows people buying bread at a bakery.
    - (2) The person standing at the front is wearing a red shirt.
    - (3) There are people lining up to take a train.
    - (4) The clerk is wearing a yellow T-shirt.
        
    정답: (4) 점원은 노란색 티셔츠가 아닌 파란색 티셔츠를 입고 있습니다.
    (주의: 정답은 1~4 중 하나만 선택되도록 출제하세요.)
    ======
    """

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": quiz_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                    },
                },
            ],
        }
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # 응답 생성에 사용할 모델을 지정
            messages=messages # 대화 기록을 입력으로 전달
        )
    except Exception as e:
        print("failed\n" + e)
        return image_quiz(image_path, n_trial+1)

    content=response.choices[0].message.content

    if "Listening:" in content:
        return content, True
    else:
        return image_quiz(image_path, n_trial+1)

q=image_quiz("../data/images/busan_dive.jpg")

print(q)

txt=''
eng_dict=[]
no=1
for g in glob('../data/images/*.jpg'):

    q, is_suceed = image_quiz(g)

    if not is_suceed:
        continue

    divider=f'## 문제 {no}\n\n'
    print(divider)
    txt += divider
    filename=os.path.basename(g)
    txt += f'![image]({filename})\n\n'

    # 문제 추가
    print(q)
    txt += q + '\n\n-------------------------------\n\n'

    with open('../data/images/image_quiz_with_eng.md','w',encoding='utf-8') as f:
        f.write(txt)

    # 영어 문제만 추출
    eng=q.split('Listening: ')[1].split('정답:')[0].strip()

    eng_dict.append({
        'no': no,
        'eng': eng,
        'img': filename
    })

    # JSON 파일로 저장
    with open('../data/images/image_quiz_eng.json','w',encoding='utf-8') as f:
        json.dump(eng_dict,f,ensure_ascii=False, indent=4)

    no += 1 # 문제 번호 증가
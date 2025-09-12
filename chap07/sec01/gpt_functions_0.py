from datetime import datetime

def get_current_time():
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(now)
    return now

tools = [
    {
        "type":"function",
        "function": {
            "name":"get_current_time",
            "description":"현재 날짜와 시간을 반환합니다.",
        }
    }
]

if __name__ == '__main__':
    get_current_time()
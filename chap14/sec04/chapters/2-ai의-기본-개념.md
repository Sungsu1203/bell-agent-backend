## 2. AI의 기본 개념

인공지능(AI)은 다양한 혁신 기술을 통해 우리 삶의 질을 향상시키고 있습니다. 하지만 AI가 어떻게 작동하는지, 그 핵심이 무엇인지 파악하기란 쉽지 않습니다. 따라서 이번 장에서는 AI의 기본 개념을 이해하는 데 도움이 되는 중요한 요소들을 설명하겠습니다. 이를 위해 머신러닝, 딥러닝, 신경망, 자연어 처리(NLP), 컴퓨터 비전 등 AI를 구성하는 주요 기술들을 차례로 다루어 보겠습니다.

### 머신러닝의 기초

**머신러닝(ML)**은 AI의 한 분야로, 데이터로부터 학습하여 결과를 예측하거나 결정을 내리는 데 중점을 둡니다. 쉽게 비유하자면, 머신러닝은 마치 스스로 운전 연습을 통해 자동차 운전 기술을 익히는 것과 비슷합니다. 기계가 다양한 주행 데이터를 분석하고 반복된 학습을 통해 최적의 주행법을 터득하는 것처럼, 머신러닝 모델도 데이터를 통해 패턴을 인식하고 학습합니다.

간단한 예제를 통해 머신러닝의 기초 개념을 살펴보겠습니다:

```python
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier

# 데이터셋 로드
iris = load_iris()
X_train, X_test, y_train, y_test = train_test_split(iris.data, iris.target, test_size=0.2, random_state=42)

# 모델 초기화 및 훈련
model = KNeighborsClassifier(n_neighbors=3)
model.fit(X_train, y_train)

# 예측 및 평가
accuracy = model.score(X_test, y_test)
print(f"모델 정확도: {accuracy:.2f}")
```

위 코드는 가장 기본적인 머신러닝 모델 중 하나인 K-최근접 이웃(K-Nearest Neighbors)을 사용하여 붓꽃(iris) 데이터를 분류하는 예제입니다. 데이터셋을 학습시키고 테스트 데이터를 예측하여 모델의 성능을 평가합니다.

### 딥러닝과 신경망 이해하기

**딥러닝**은 대량의 데이터를 처리하여 복잡한 문제를 해결하는 AI 기술로, **신경망**이라는 수학적 구조에 기반을 두고 있습니다. 신경망은 인간의 뇌 구조를 본떠 설계되어 여러 층(layer)로 구성된 노드(node)가 서로 연결되어 정보를 처리합니다. 딥러닝은 이러한 신경망을 깊게 쌓아 복잡한 문제에서 높은 성능을 발휘합니다.

딥러닝의 매력을 단순한 블록 놀이라는 비유로 설명할 수 있습니다. 하나의 블록은 단순한 연산에 불과하지만, 블록을 여러 층으로 쌓으면 복잡한 구조물을 만들 수 있듯, 딥러닝도 여러 층의 신경망을 이용해 고도화된 분석과 예측을 수행합니다.

### 자연어 처리(NLP)의 역할

**자연어 처리(NLP)**는 인간의 언어를 이해하고 생성하며, 인간과 기계 간의 원활한 소통을 가능하게 합니다. 예를 들어, 고객 지원 챗봇은 NLP 기술을 사용해 고객의 질문을 이해하고 정확한 정보를 제공합니다. 

NLP는 언어와 문맥을 이해하기 위해 텍스트 데이터를 분석하고 처리하며, 이를 통해 문장을 생성하거나 번역할 수 있습니다. 영화 리뷰 감정을 분석하는 간단한 실습을 해보겠습니다.

```python
from textblob import TextBlob

# 예제 리뷰
review = "The movie was a fantastic journey into the realm of fantasy."
# 리뷰 감정 분석
analysis = TextBlob(review)
sentiment = analysis.sentiment.polarity
print(f"리뷰 감정 점수: {sentiment:.2f}")
```

여기서 `TextBlob` 라이브러리는 우리가 제공한 텍스트의 감정 점수를 계산하여 긍정적, 부정적 여부를 파악합니다.

### 컴퓨터 비전의 응용

**컴퓨터 비전**은 기계가 이미지나 비디오로부터 의미 있는 정보를 추출할 수 있도록 돕는 AI 기술입니다. 이 기술은 자율주행차의 물체 인식, 얼굴 인식 애플리케이션 등 다양한 영역에서 사용됩니다. 예를 들어, 자율주행차는 카메라와 센서를 통해 도로 상황과 보행자를 인식하여 안전한 주행을 지원합니다.

이제 이미지를 분류하는 간단한 예제를 진행해보겠습니다. 

```python
from tensorflow.keras.datasets import mnist
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Flatten

# MNIST 데이터셋 로드
(x_train, y_train), (x_test, y_test) = mnist.load_data()

# 모델 생성
model = Sequential([
    Flatten(input_shape=(28, 28)),
    Dense(128, activation='relu'),
    Dense(10, activation='softmax')
])

# 모델 컴파일 및 훈련
model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
model.fit(x_train, y_train, epochs=5, validation_data=(x_test, y_test))
```

이 코드는 손글씨 숫자 이미지 데이터를 사용하여 0부터 9까지의 숫자를 인식하도록 훈련하는 간단한 신경망 모델을 구현한 것입니다.

### 핵심 요약
- 머신러닝은 데이터를 통해 패턴을 학습하여 예측 모델을 만듦.
- 딥러닝은 여러 층으로 이루어진 신경망을 통해 복잡한 문제를 해결.
- 자연어 처리는 사람의 언어를 이해·생성하여 기계와의 소통을 향상.
- 컴퓨터 비전은 이미지와 비디오 분석을 통해 시각적 정보 이해를 지원. 

이 장에서는 AI의 기본 개념을 소개했습니다. 이제 AI 기술들이 어떻게 상호작용하여 현실 세계에 적용되는지 이해하셨기를 바랍니다.
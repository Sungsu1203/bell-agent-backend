from tools.web_rag.utils import _normalize_canonical_url, make_doc_id

def doc_id_single(src: str, ver: str, text: str) -> str:
    counter = {}
    return make_doc_id(
        src,
        ver,
        text,
        counter=counter,
        max_id_chars=128,
    )

def doc_id_double(src: str, ver: str, text: str) -> str:
    # 이전 구조(로컬에서 1번 canonical 후 make_doc_id가 다시 canonical) 시뮬레이션
    src2 = _normalize_canonical_url(src)
    counter = {}
    return make_doc_id(
        src2,
        ver,
        text,
        counter=counter,
        max_id_chars=128,
    )

if __name__ == "__main__":
    ver = "1700000000"
    text = "hello world"

    cases = [
        "file:///C:/DATA/a.pdf#part=Slide&index=1&chunk=0",
        "file:///c:/data/a.pdf#chunk=0&index=1&part=Slide",
        "file:///C:/data/a.pdf#part=Slide&chunk=0&index=1",
    ]

    print("=== normalize 결과 비교 ===")
    norms = []
    for i, src in enumerate(cases, 1):
        n = _normalize_canonical_url(src)
        norms.append(n)
        print(f"[{i}] raw : {src}")
        print(f"    norm: {n}")

    print("\n=== 케이스 간 normalize 동일? ===")
    for i in range(len(norms)):
        for j in range(i + 1, len(norms)):
            print(f"norm[{i+1}] == norm[{j+1}] ? {norms[i] == norms[j]}")

    print("\n=== doc_id(single) 비교 ===")
    ids_single = [doc_id_single(s, ver, text) for s in cases]
    for i, did in enumerate(ids_single, 1):
        print(f"[{i}] {did}")
    for i in range(len(ids_single)):
        for j in range(i + 1, len(ids_single)):
            print(f"id_single[{i+1}] == id_single[{j+1}] ? {ids_single[i] == ids_single[j]}")

    print("\n=== doc_id(double) 비교 (참고) ===")
    ids_double = [doc_id_double(s, ver, text) for s in cases]
    for i, did in enumerate(ids_double, 1):
        print(f"[{i}] {did}")
    for i in range(len(ids_double)):
        for j in range(i + 1, len(ids_double)):
            print(f"id_double[{i+1}] == id_double[{j+1}] ? {ids_double[i] == ids_double[j]}")

    print("\n=== single vs double (각 케이스별) ===")
    for i, src in enumerate(cases, 1):
        s_id = doc_id_single(src, ver, text)
        d_id = doc_id_double(src, ver, text)
        print(f"[{i}] same? {s_id == d_id}")
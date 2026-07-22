# 06 — UAE Expansion: Issues & Pre-emptive Design

**Target:** Dubai → Abu Dhabi (Phase 2, M7-M12)
**Purpose:** M1-M6 진행 중에 미리 대비해야 할 것들, 그리고 M7 착수 시 예상 이슈

---

## 1. Why UAE

- 세계에서 가장 RWA 친화적 규제 (VARA in Dubai, FSRA in ADGM)
- 부동산 시장 규모 크고 외국인 소유 활발 (freehold zones)
- DLD (Dubai Land Department)가 블록체인·데이터 개방 우호적
- 이슬람 금융 허브 — 스쿠크 구조와의 미래 연결 가능성

---

## 2. Key Differences vs Korea (미리 알아둘 것)

### 2.1 데이터 접근

| 항목 | 한국 | 두바이 | 아부다비 |
|---|---|---|---|
| 실거래 오픈데이터 | ✅ MOLIT 완전 개방 | ⚠️ DLD 일부 공개 | ❌ 제한적 |
| 등기 시스템 | 완전 디지털 | Ejari + Oqood | Tamm platform |
| 시세 데이터 | 관·민 다수 | Bayut, PF, RG | 유사 |
| 자유 API | 무료 | 유료·B2B 협의 | B2B 협의 |
| 데이터 언어 | 한국어 | 아랍어 + 영어 | 아랍어 + 영어 |

**시사점**: 두바이는 데이터 확보를 위해 **DLD·프롭테크 파트너십**이 필수. 한국처럼 무료 대량 수집 어려움. **비용 예산에 이 부분 반드시 반영**.

### 2.2 자산 특성

| 항목 | 한국 | UAE |
|---|---|---|
| 지배적 유형 | 아파트 (표준화 高) | 아파트 + 빌라 혼재 |
| 소유권 구조 | 대부분 freehold/strata | Freehold zone / Leasehold / Musataha 혼재 |
| 신축 비중 | 안정 시장 | Off-plan (분양권) 매우 활발 |
| 통화 | KRW 단일 | AED (USD 페그) |
| 계절성 | 있음 | 미미 |
| 외국인 소유 제한 | 낮음 | Zone별 상이 |

**스키마 영향**:
- `ownership_type`에 `MUSATAHA` 이미 포함 ✅
- `property_type`에 `VILLA` 이미 포함 ✅
- `is_offplan` boolean 필드 추가 필요 (분양권 여부)
- `foreign_ownership_eligible` boolean 필드 추가 필요

**AVM 영향**:
- Villa는 아파트와 완전히 다른 모델 (면적·토지·건물 분리)
- Off-plan은 handover date가 target 시점 다름 → 별도 모델
- Community 단위 통계가 지역 통계보다 중요

### 2.3 규제

| 항목 | 한국 | 두바이 | 아부다비 |
|---|---|---|---|
| 부동산 감정 자격 | 감정평가사 (독점) | RERA registered valuer | ADREC valuer |
| 온체인 자산 규제 | 애매 | VARA 프레임 명확 | ADGM FSRA |
| 데이터 프라이버시 | PIPA | UAE PDPL | ADGM Data Protection |
| 감정 리포트 법적 지위 | 감정평가법 | RERA circulars | ADGM regs |

**시사점**:
- 두바이가 규제 명확성 면에서 압도적 유리 → Phase 2 착수 우선지
- Attestation을 "감정평가"로 부르면 자격 문제 발생 가능 → "**Valuation Estimate**"·"Reference Value" 용어 사용
- 실제 감정 리포트 대체가 아닌 **보조 신호**로 포지셔닝

### 2.4 문화·비즈니스 관행

- 부동산 개발사 파워풀 (Emaar, Damac, Nakheel, Aldar) — 파트너십 필수
- Off-plan에 대한 투자 관행이 시장 유동성의 큰 비중
- 커뮤니티 브랜드 프리미엄 큼 (Palm, Downtown, JBR, Saadiyat)
- 임대 수익률(gross yield)이 매매가와 강하게 연동 — Income approach가 한국보다 중요

---

## 3. Impact on Current MVP Design

### 3.1 스키마에 미리 반영할 것 (M1)

지금 만드는 스키마에 다음 필드/enum을 **미리 포함**:

```python
# packages/core/schemas.py 추가
class Property(BaseModel):
    # ... existing ...
    is_offplan: bool = False
    expected_handover_date: Optional[date] = None
    foreign_ownership_eligible: Optional[bool] = None
    community_id: Optional[str] = None  # UAE community 단위
    community_name: Optional[str] = None
    # ... 
```

Enum 추가:
```python
class OwnershipType(StrEnum):
    # ...
    MUSATAHA = "MUSATAHA"  # UAE 50-year development right
    OFFPLAN = "OFFPLAN"    # 분양권
```

DB migration으로 M1에 미리 반영. 사용은 M7부터지만 스키마 흔들지 않음.

### 3.2 어댑터 인터페이스에 미리 반영할 것 (M2)

`CountryAdapter` 인터페이스에 다음 옵셔널 메서드 추가:

```python
class CountryAdapter(ABC):
    # ... existing ...
    
    async def fetch_offplan_registry(self, developer: str) -> AsyncIterator[Property]:
        """Off-plan property registry. KR adapter는 raise NotImplementedError."""
        raise NotImplementedError
    
    async def fetch_lease_yields(self, region: str, ymd: str) -> AsyncIterator[YieldData]:
        """Rental yield data. Income approach용."""
        raise NotImplementedError
```

인터페이스만 확장하고 KR은 미구현. AE 어댑터가 오면 구현.

### 3.3 AVM 아키텍처에 미리 반영할 것 (M3)

**Model registry의 스코프 필드**:
```
model_id: avm-{country}-{region}-{property_type}-v{n}-{date}-{sha}
```

예:
- `avm-kr-seoul-apt-v3-20260315-a3f8c2`
- `avm-ae-dubai-apt-v1-20260901-b7c1d3`
- `avm-ae-dubai-villa-v1-20260901-b7c1d3`

Model registry는 이걸 처음부터 지원 (property_type을 스코프에 포함).

**Feature 라이브러리 모듈화**:
```
packages/avm/features/
├── common/          # 모든 국가 공통 (age, floor ratio, log-transform)
├── kr/              # 한국 특화 (subway_lines, 학군)
├── ae/              # UAE 특화 (community_score, developer_tier, yield)
└── registry.py
```

### 3.4 Move 컨트랙트에 미리 반영할 것 (M5)

- `Property.property_type` field는 string (enum extensible) ✅
- Country code는 registry-controlled 진입 ✅
- Attestation의 `method` enum에 여지 확보 ✅

**추가 고려**:
- UAE는 Shariah compliance 필요할 수 있음 → 추후 attestation의 `flags: vector<String>` dynamic field로 확장
- 지금 하드코딩 회피

---

## 4. Data Source Deep Dive (Dubai)

### 4.1 DLD (Dubai Land Department)

- Website: https://dubailand.gov.ae
- Open Data Portal: 일부 통계·거래 데이터 공개
- **Transactions Dataset**: 매매·임대 매월 발표 (CSV, 지연 있음)
- 실시간 API는 별도 협의 필요
- **접근 전략**:
  - Phase 1: 공개 데이터셋 수집 (M6에 시작)
  - Phase 2: DLD 파트너십 접촉 (M7-M8)
  - Phase 3: 데이터 API 계약 (M9+)

### 4.2 Property Finder / Bayut / Dubizzle

- 시세·매물 데이터
- Bayut API: B2B 유료
- Property Finder: 파트너십
- 크롤링은 ToS 위반 가능성

### 4.3 REIDIN / Cavendish Maxwell / DAMAC 리서치

- 유료 리서치·지수 데이터
- 검증·벤치마크용

### 4.4 CBRE / JLL / Cushman & Wakefield

- 상업용·프라임 데이터
- 파트너십 통한 감정사 네트워크 확보 후보

---

## 5. Data Source Deep Dive (Abu Dhabi)

### 5.1 DMT / TAMM

- Abu Dhabi Department of Municipalities and Transport
- TAMM 플랫폼: 정부 서비스 통합
- 데이터 개방도 두바이보다 낮음
- 파트너십 통해 접근 필요

### 5.2 ADREC (Abu Dhabi Real Estate Centre)

- 감정평가사 등록 기관
- 감정사 네트워크 파트너십 대상

### 5.3 시사점

아부다비는 두바이보다 6개월 이상 뒤에. **두바이에서 프로덕트 검증 후 진입**.

---

## 6. Partnership Roadmap

### 6.1 우선순위

1. **DLD** — 데이터 파트너십 (M6부터 접촉)
2. **VARA** — 규제 프레임 사전 상담 (M6-M7)
3. **Bayut / Property Finder** — 시세 데이터 (M7)
4. **RERA 등록 감정사** — 개별 온보딩 (M8-M9)
5. **개발사 (Emaar, Damac)** — off-plan 데이터 (M9-M10)
6. **ADGM (Abu Dhabi)** — 아부다비 진출 전 (M11+)

### 6.2 파트너십 자산

두바이 진입 시 우리가 들고 갈 것:
- 한국 백테스트 백서 (신뢰의 증거)
- Sui Testnet에 발행된 만 건+ attestation
- 오픈소스 코드베이스
- 국제 정규화 스키마 (다국가 지원 이미 증명)

---

## 7. Timeline (Phase 2)

### M7 (Month 7)
- DLD 데이터 조사, 공개 데이터셋 수집·정규화
- UAE 어댑터 skeleton (`packages/adapter-ae/`)
- 아랍어 주소 정규화 라이브러리 조사
- VARA 규제 미팅 준비

### M8
- 두바이 아파트 5년치 매매 데이터 확보
- Villa 스키마 확장 완성
- Community-level POI 데이터 (school, mall, metro, beach)
- 아랍어·영어 지오코딩

### M9
- AE Dubai APT AVM v1
- Villa 별도 AVM 착수
- Off-plan 처리 로직

### M10
- Testnet에 UAE adapter cap 등록
- Dubai 아파트 attestation 발행 시작
- KR과 UAE 통합 API

### M11
- Dubai 백테스트 리포트
- Bayut/PF 데이터 대조 검증
- Abu Dhabi 데이터 착수

### M12
- 파트너 프로토콜 온보딩 (Dubai)
- Mainnet 준비

---

## 8. Pre-emptive Design Checklist (M1-M6 중 반드시)

M6까지 다음 사항을 반드시 준비해 두면 두바이 확장이 매끄러워짐:

- [ ] 스키마에 UAE-required 필드·enum 미리 포함 (is_offplan, community_id, MUSATAHA 등)
- [ ] Currency handling에 AED 미리 지원 (FX rate 테이블 스키마)
- [ ] 주소 정규화기 인터페이스가 아랍어 지원 확장 가능하도록 (unicode-safe)
- [ ] Model registry가 property_type·region까지 세분화된 스코프 지원
- [ ] Feature engineering 라이브러리 모듈화 (`common` vs country-specific)
- [ ] Move의 `Property.property_type` 확장성 확인
- [ ] Attestation의 `method`·flags 확장 여지 확보
- [ ] 문서·README·API 스펙에 "country-agnostic core" 원칙 명시

---

## 9. Risks Specific to UAE

| 리스크 | 완화 |
|---|---|
| 데이터 접근 지연 | Public dataset부터 시작, 파트너십 병행 |
| 아랍어 처리 복잡성 | ICU library 사용, 전문가 자문 |
| Off-plan 위험도 높음 | 초기엔 handover 완료 물건만 |
| 개발사 로비 (자기 프로젝트 가치 부풀리기) | Community-level 통계에 무게 |
| RERA 감정사 협회 반발 | "감정사 도구" 포지셔닝 견지 |
| 지정학 리스크 | UAE 이외 대안 옵션 (싱가포르·한국 심화) 상시 검토 |

---

## 10. Success Criteria (Phase 2 완료)

- [ ] Dubai 아파트 AVM MdAPE ≤ 8%
- [ ] Dubai 아파트 10,000건+ attestation
- [ ] Villa AVM 파일럿 (MdAPE 목표는 별도 정의)
- [ ] DLD·VARA와 공식 관계 수립
- [ ] Dubai 백테스트 백서 공개
- [ ] 한국·두바이 통합 API 서빙
- [ ] Abu Dhabi 데이터 파이프라인 착수

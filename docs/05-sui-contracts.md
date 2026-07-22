# 05 — Sui Move Contracts

**Package:** `packages/move/valis/`
**Network:** Sui Testnet (M5), Mainnet (post-M6)

---

## 1. Design Goals

1. **국가 어댑터를 온체인 identity로 관리** — 승인된 어댑터만 property 등록 가능
2. **Property Object = 실물 자산 1:1 매핑** — 결정론적 `global_id` seed
3. **Attestation을 owned object로** — 파트너 프로토콜이 소비·검증 가능
4. **Oracle feed 패턴 지원** — 최신 attestation을 shared object로 조회
5. **모듈 간 관심사 분리** — Registry, Attestation, Oracle, Adapter를 명확히
6. **Upgrade-friendly** — Sui의 package upgrade 정책 대비, migration path 확보

---

## 2. Package Structure

```
packages/move/valis/
├── Move.toml
├── sources/
│   ├── country_adapter.move    # 국가 어댑터 registry + capabilities
│   ├── property_registry.move  # Property object + registration
│   ├── attestation.move        # AppraisalAttestation object
│   ├── oracle_feed.move        # Shared object for latest values
│   ├── issuer.move             # Attestation issuer capability
│   ├── events.move             # Event definitions
│   └── errors.move             # Error codes
├── tests/
│   ├── property_registry_tests.move
│   ├── attestation_tests.move
│   └── oracle_feed_tests.move
└── scripts/
    ├── deploy_testnet.ts
    └── seed_adapters.ts
```

---

## 3. Move Code Skeleton

### 3.1 `errors.move`

```move
module valis::errors {
    const ENotAuthorized: u64 = 1;
    const EInvalidCountryCode: u64 = 2;
    const EPropertyAlreadyRegistered: u64 = 3;
    const EPropertyNotFound: u64 = 4;
    const EAttestationExpired: u64 = 5;
    const EInvalidConfidence: u64 = 6;
    const EAdapterNotActive: u64 = 7;
    const EInvalidValuation: u64 = 8;
    const EAttestationRevoked: u64 = 9;
    
    public fun not_authorized(): u64 { ENotAuthorized }
    public fun invalid_country(): u64 { EInvalidCountryCode }
    public fun property_exists(): u64 { EPropertyAlreadyRegistered }
    public fun property_not_found(): u64 { EPropertyNotFound }
    public fun attestation_expired(): u64 { EAttestationExpired }
    public fun invalid_confidence(): u64 { EInvalidConfidence }
    public fun adapter_inactive(): u64 { EAdapterNotActive }
    public fun invalid_valuation(): u64 { EInvalidValuation }
    public fun revoked(): u64 { EAttestationRevoked }
}
```

### 3.2 `country_adapter.move`

```move
module valis::country_adapter {
    use std::string::{Self, String};
    use sui::object::{Self, UID, ID};
    use sui::tx_context::TxContext;
    use sui::event;
    use valis::errors;

    /// Admin capability for the whole protocol
    public struct ProtocolAdminCap has key, store {
        id: UID,
    }

    /// Capability granted to an approved country adapter
    /// Only the holder can register properties for that country
    public struct CountryAdapterCap has key, store {
        id: UID,
        country_code: String,   // ISO 3166-1 alpha-2, uppercase
        issued_at: u64,
        is_active: bool,
    }

    /// Registry of active country adapters (shared object)
    public struct AdapterRegistry has key {
        id: UID,
        // country_code => cap_id
        adapters: sui::table::Table<String, ID>,
    }

    // === Events ===
    public struct AdapterRegistered has copy, drop {
        cap_id: ID,
        country_code: String,
    }

    public struct AdapterDeactivated has copy, drop {
        cap_id: ID,
        country_code: String,
    }

    // === Init ===
    fun init(ctx: &mut TxContext) {
        let admin = ProtocolAdminCap { id: object::new(ctx) };
        sui::transfer::transfer(admin, sui::tx_context::sender(ctx));

        let registry = AdapterRegistry {
            id: object::new(ctx),
            adapters: sui::table::new(ctx),
        };
        sui::transfer::share_object(registry);
    }

    // === Entry: Admin registers a new country adapter ===
    public entry fun register_adapter(
        _admin: &ProtocolAdminCap,
        registry: &mut AdapterRegistry,
        country_code: vector<u8>,
        recipient: address,
        clock: &sui::clock::Clock,
        ctx: &mut TxContext,
    ) {
        let cc = string::utf8(country_code);
        assert!(string::length(&cc) == 2, errors::invalid_country());
        assert!(!sui::table::contains(&registry.adapters, cc), errors::property_exists());

        let cap = CountryAdapterCap {
            id: object::new(ctx),
            country_code: cc,
            issued_at: sui::clock::timestamp_ms(clock),
            is_active: true,
        };
        let cap_id = object::id(&cap);
        sui::table::add(&mut registry.adapters, cc, cap_id);

        event::emit(AdapterRegistered { cap_id, country_code: cc });
        sui::transfer::transfer(cap, recipient);
    }

    // === Query ===
    public fun country_code(cap: &CountryAdapterCap): &String { &cap.country_code }
    public fun is_active(cap: &CountryAdapterCap): bool { cap.is_active }

    // === Deactivation ===
    public entry fun deactivate(
        _admin: &ProtocolAdminCap,
        registry: &mut AdapterRegistry,
        cap_country_code: vector<u8>,
    ) {
        let cc = string::utf8(cap_country_code);
        let cap_id = *sui::table::borrow(&registry.adapters, cc);
        event::emit(AdapterDeactivated { cap_id, country_code: cc });
        sui::table::remove(&mut registry.adapters, cc);
    }
}
```

### 3.3 `property_registry.move`

```move
module valis::property_registry {
    use std::string::{Self, String};
    use sui::object::{Self, UID};
    use sui::tx_context::TxContext;
    use sui::event;
    use sui::dynamic_field as df;
    use valis::country_adapter::CountryAdapterCap;
    use valis::errors;

    /// A property registered in the protocol.
    /// The `global_id` is the sha256 hash of `country_code:local_id_canonical`
    /// computed off-chain, ensuring deterministic deduplication.
    public struct Property has key, store {
        id: UID,
        global_id: vector<u8>,         // 32 bytes sha256
        country_code: String,
        local_id_canonical: String,
        property_type: String,         // enum as string
        registered_at: u64,
        registered_by: address,        // adapter that registered
        // Dynamic fields for extensibility:
        //   b"geo" => GeoData
        //   b"metrics" => PropertyMetrics
        //   b"latest_attestation" => ID (link to latest attestation)
    }

    public struct GeoData has store, drop {
        latitude_e7: i64,
        longitude_e7: i64,
        admin_level_1: String,
        admin_level_2: String,
        admin_level_3: String,
    }

    public struct PropertyMetrics has store, drop {
        net_area_sqm_x100: u64,        // sqm × 100
        built_year: u16,
        floors_total: u16,
        floor_number: u16,
    }

    /// Shared object that maps global_id -> Property object id
    /// Ensures no duplicate registration across the protocol.
    public struct PropertyIndex has key {
        id: UID,
        by_global_id: sui::table::Table<vector<u8>, sui::object::ID>,
    }

    // === Events ===
    public struct PropertyRegistered has copy, drop {
        property_id: sui::object::ID,
        global_id: vector<u8>,
        country_code: String,
    }

    // === Init ===
    fun init(ctx: &mut TxContext) {
        let index = PropertyIndex {
            id: object::new(ctx),
            by_global_id: sui::table::new(ctx),
        };
        sui::transfer::share_object(index);
    }

    // === Entry: adapter registers a property ===
    public entry fun register(
        adapter_cap: &CountryAdapterCap,
        index: &mut PropertyIndex,
        global_id: vector<u8>,
        local_id_canonical: vector<u8>,
        property_type: vector<u8>,
        // GeoData
        latitude_e7: i64,
        longitude_e7: i64,
        admin_1: vector<u8>,
        admin_2: vector<u8>,
        admin_3: vector<u8>,
        // Metrics
        net_area_sqm_x100: u64,
        built_year: u16,
        floors_total: u16,
        floor_number: u16,
        clock: &sui::clock::Clock,
        ctx: &mut TxContext,
    ) {
        assert!(valis::country_adapter::is_active(adapter_cap), errors::adapter_inactive());
        assert!(std::vector::length(&global_id) == 32, errors::invalid_valuation());
        assert!(!sui::table::contains(&index.by_global_id, global_id), errors::property_exists());

        let country_code = *valis::country_adapter::country_code(adapter_cap);
        let now = sui::clock::timestamp_ms(clock);

        let mut prop = Property {
            id: object::new(ctx),
            global_id,
            country_code,
            local_id_canonical: string::utf8(local_id_canonical),
            property_type: string::utf8(property_type),
            registered_at: now,
            registered_by: sui::tx_context::sender(ctx),
        };

        df::add(&mut prop.id, b"geo", GeoData {
            latitude_e7,
            longitude_e7,
            admin_level_1: string::utf8(admin_1),
            admin_level_2: string::utf8(admin_2),
            admin_level_3: string::utf8(admin_3),
        });

        df::add(&mut prop.id, b"metrics", PropertyMetrics {
            net_area_sqm_x100,
            built_year,
            floors_total,
            floor_number,
        });

        let prop_id = object::id(&prop);
        sui::table::add(&mut index.by_global_id, global_id, prop_id);

        event::emit(PropertyRegistered {
            property_id: prop_id,
            global_id,
            country_code,
        });

        // Share so anyone can attach attestations to it via oracle feed
        sui::transfer::share_object(prop);
    }

    // === Queries ===
    public fun global_id(p: &Property): &vector<u8> { &p.global_id }
    public fun country_code(p: &Property): &String { &p.country_code }
    public fun uid_mut(p: &mut Property): &mut UID { &mut p.id }
    public fun uid(p: &Property): &UID { &p.id }

    public fun lookup(index: &PropertyIndex, global_id: vector<u8>): sui::object::ID {
        *sui::table::borrow(&index.by_global_id, global_id)
    }
}
```

### 3.4 `attestation.move`

```move
module valis::attestation {
    use std::string::{Self, String};
    use sui::object::{Self, UID};
    use sui::tx_context::TxContext;
    use sui::event;
    use valis::property_registry::Property;
    use valis::errors;

    /// A single appraisal attestation.
    /// This is an owned object — the issuer holds it after mint,
    /// then transfers to a subscriber or attaches to a shared feed.
    public struct AppraisalAttestation has key, store {
        id: UID,
        property_id: sui::object::ID,
        property_global_id: vector<u8>,
        value_usd_cents: u64,
        ci_lower_usd_cents: u64,
        ci_upper_usd_cents: u64,
        confidence_bps: u16,           // 0-10000
        method: u8,                    // 0:AVM 1:CONSENSUS 2:HYBRID
        model_id: String,
        report_uri: String,            // walrus:// or ipfs:// or https://
        report_hash: vector<u8>,       // 32 bytes sha256
        issued_at: u64,
        expires_at: u64,
        issuer: address,
        is_revoked: bool,
    }

    /// Capability held by the protocol's issuer service.
    public struct IssuerCap has key, store {
        id: UID,
        allowed_methods: vector<u8>,   // e.g. [0, 2] for AVM + HYBRID
    }

    // === Events ===
    public struct AttestationIssued has copy, drop {
        attestation_id: sui::object::ID,
        property_id: sui::object::ID,
        property_global_id: vector<u8>,
        value_usd_cents: u64,
        confidence_bps: u16,
        method: u8,
        model_id: String,
    }

    public struct AttestationRevoked has copy, drop {
        attestation_id: sui::object::ID,
        reason: String,
    }

    // === Entry: mint attestation ===
    public entry fun issue(
        cap: &IssuerCap,
        property: &Property,
        value_usd_cents: u64,
        ci_lower_usd_cents: u64,
        ci_upper_usd_cents: u64,
        confidence_bps: u16,
        method: u8,
        model_id: vector<u8>,
        report_uri: vector<u8>,
        report_hash: vector<u8>,
        validity_ms: u64,
        clock: &sui::clock::Clock,
        recipient: address,
        ctx: &mut TxContext,
    ) {
        assert!(value_usd_cents > 0, errors::invalid_valuation());
        assert!(ci_lower_usd_cents <= value_usd_cents, errors::invalid_valuation());
        assert!(ci_upper_usd_cents >= value_usd_cents, errors::invalid_valuation());
        assert!(confidence_bps <= 10000, errors::invalid_confidence());
        assert!(std::vector::length(&report_hash) == 32, errors::invalid_valuation());
        assert!(is_method_allowed(cap, method), errors::not_authorized());

        let now = sui::clock::timestamp_ms(clock);
        let att = AppraisalAttestation {
            id: object::new(ctx),
            property_id: object::id(property),
            property_global_id: *valis::property_registry::global_id(property),
            value_usd_cents,
            ci_lower_usd_cents,
            ci_upper_usd_cents,
            confidence_bps,
            method,
            model_id: string::utf8(model_id),
            report_uri: string::utf8(report_uri),
            report_hash,
            issued_at: now,
            expires_at: now + validity_ms,
            issuer: sui::tx_context::sender(ctx),
            is_revoked: false,
        };

        event::emit(AttestationIssued {
            attestation_id: object::id(&att),
            property_id: att.property_id,
            property_global_id: att.property_global_id,
            value_usd_cents,
            confidence_bps,
            method,
            model_id: att.model_id,
        });

        sui::transfer::public_transfer(att, recipient);
    }

    public entry fun revoke(
        _cap: &IssuerCap,
        att: &mut AppraisalAttestation,
        reason: vector<u8>,
    ) {
        att.is_revoked = true;
        event::emit(AttestationRevoked {
            attestation_id: object::id(att),
            reason: string::utf8(reason),
        });
    }

    // === Queries ===
    public fun value_usd_cents(a: &AppraisalAttestation): u64 { a.value_usd_cents }
    public fun confidence_bps(a: &AppraisalAttestation): u16 { a.confidence_bps }
    public fun is_valid(a: &AppraisalAttestation, clock: &sui::clock::Clock): bool {
        !a.is_revoked && sui::clock::timestamp_ms(clock) < a.expires_at
    }

    fun is_method_allowed(cap: &IssuerCap, method: u8): bool {
        std::vector::contains(&cap.allowed_methods, &method)
    }
}
```

### 3.5 `oracle_feed.move`

```move
module valis::oracle_feed {
    use sui::object::{Self, UID, ID};
    use sui::tx_context::TxContext;
    use sui::event;
    use valis::attestation::{Self, AppraisalAttestation};

    /// Shared object that partners can read to get the latest
    /// valuation for a property without holding the attestation.
    public struct ValuationFeed has key {
        id: UID,
        // global_id (32 bytes) => FeedEntry
        entries: sui::table::Table<vector<u8>, FeedEntry>,
    }

    public struct FeedEntry has store, drop {
        attestation_id: ID,
        value_usd_cents: u64,
        confidence_bps: u16,
        updated_at: u64,
        expires_at: u64,
    }

    public struct FeedUpdated has copy, drop {
        global_id: vector<u8>,
        attestation_id: ID,
        value_usd_cents: u64,
    }

    fun init(ctx: &mut TxContext) {
        let feed = ValuationFeed {
            id: object::new(ctx),
            entries: sui::table::new(ctx),
        };
        sui::transfer::share_object(feed);
    }

    /// The attestation holder can publish it to the feed.
    /// Feed always keeps only the latest attestation per property.
    public entry fun publish(
        feed: &mut ValuationFeed,
        att: &AppraisalAttestation,
        clock: &sui::clock::Clock,
    ) {
        assert!(attestation::is_valid(att, clock), 100);

        let global_id = *valis::attestation_helper::property_global_id(att);
        let entry = FeedEntry {
            attestation_id: object::id(att),
            value_usd_cents: attestation::value_usd_cents(att),
            confidence_bps: attestation::confidence_bps(att),
            updated_at: sui::clock::timestamp_ms(clock),
            expires_at: valis::attestation_helper::expires_at(att),
        };

        if (sui::table::contains(&feed.entries, global_id)) {
            let _old = sui::table::remove(&mut feed.entries, global_id);
        };
        sui::table::add(&mut feed.entries, global_id, entry);

        event::emit(FeedUpdated {
            global_id,
            attestation_id: entry.attestation_id,
            value_usd_cents: entry.value_usd_cents,
        });
    }

    public fun get(feed: &ValuationFeed, global_id: vector<u8>): (u64, u16, u64) {
        let entry = sui::table::borrow(&feed.entries, global_id);
        (entry.value_usd_cents, entry.confidence_bps, entry.updated_at)
    }
}
```

*Note: `attestation_helper`는 attestation 모듈에 아래 헬퍼를 추가하거나, cross-module read access를 위한 friend/public accessor를 정의.*

---

## 4. Off-chain Integration

### 4.1 Attestation Issuer Service

Python service in `packages/attestation`:

```python
# packages/attestation/issuer.py
from pysui import SuiConfig, AsyncClient
from pysui.sui.sui_txn import AsyncTransaction

class AttestationIssuer:
    def __init__(self, config: SuiConfig, package_id: str, issuer_cap_id: str):
        self.client = AsyncClient(config)
        self.package_id = package_id
        self.issuer_cap_id = issuer_cap_id
    
    async def register_property(
        self, adapter_cap_id: str, property_data: Property, ...
    ):
        """Call country_adapter-gated register."""
    
    async def issue_attestation(
        self, property_id: str, prediction: AVMPrediction,
        recipient: str,
    ) -> str:
        """Mint AppraisalAttestation, return Sui object id."""
    
    async def publish_to_feed(self, attestation_id: str, feed_id: str):
        """Push to ValuationFeed shared object."""
```

### 4.2 Batch Flow

```
scripts/issue_attestations.py
  1. Query DB: properties needing attestation (new or expiring)
  2. Run AVM prediction batch
  3. Upload detailed reports to Walrus/R2, get URI + hash
  4. For each:
     a. If Property not yet on-chain → register (via adapter cap)
     b. Issue AppraisalAttestation
     c. Publish to ValuationFeed
  5. Store sui_tx_digest + attestation_uid in DB
```

Rate limit consideration: Sui Testnet 부하 고려해서 초당 5–10 tx 정도로. PTB로 register + issue + publish를 한 tx에 묶기.

---

## 5. Deployment

### 5.1 Deploy Steps

```bash
# 1. Build
cd packages/move/valis
sui move build

# 2. Publish to testnet
sui client publish --gas-budget 100000000

# 3. Record IDs
# - package_id
# - AdapterRegistry (shared)
# - PropertyIndex (shared)
# - ValuationFeed (shared)
# - ProtocolAdminCap (owned by deployer)

# 4. Register Korea adapter
sui client call \
  --package $PACKAGE_ID \
  --module country_adapter \
  --function register_adapter \
  --args $ADMIN_CAP $REGISTRY 0x4b52 $ISSUER_ADDR $CLOCK

# 5. Create Issuer Capability manually (via internal script)
```

### 5.2 Environment Variables

```
SUI_NETWORK=testnet
SUI_RPC_URL=https://fullnode.testnet.sui.io:443
SUI_PACKAGE_ID=0x...
SUI_ADAPTER_REGISTRY_ID=0x...
SUI_PROPERTY_INDEX_ID=0x...
SUI_VALUATION_FEED_ID=0x...
SUI_ISSUER_CAP_ID=0x...
SUI_ADMIN_CAP_ID=0x...
SUI_ISSUER_PRIVKEY=  # only in Railway secret
SUI_CLOCK_ID=0x6
```

### 5.3 Testnet reset resilience

- 배포 스크립트는 idempotent
- DB에 `sui_deployment` 테이블: `package_id`, `network`, `deployed_at`
- Testnet reset 감지 시 → 재배포 → 기존 attestation 재발급 필요

---

## 6. Testing

### 6.1 Move unit tests

`tests/*.move`:
- Property registration flow (success + duplicate rejection)
- Attestation issue with valid/invalid CI bounds
- Feed publish → get consistency
- Adapter cap authorization enforcement
- Revocation flow
- Expiration boundary conditions

### 6.2 Integration tests

Python + testnet:
- End-to-end: DB Property → register → issue → publish → query feed
- Multiple attestations for same property (feed always latest)
- Adapter deactivation prevents new registration

### 6.3 Gas benchmarks

- 각 entry function 별 gas cost 측정
- PTB 조합 시 gas 최적화
- 목표: 발행당 attestation < $0.05 gas equivalent

---

## 7. Upgrade Strategy

Sui의 Move package upgrade는 immutable objects·public function 시그니처 변경 제약.

- 초기 배포는 `--upgrade-policy compatible`
- Breaking change 필요 시:
  1. 새 package 배포
  2. Registry migration script로 기존 Property 재발급
  3. Feed URL 갱신 공지
- Attestation 데이터 구조 변경은 최소화 (extended fields는 dynamic field로)

---

## 8. Deliverables (M5)

- [ ] Move 모듈 5개 구현·컴파일
- [ ] Move 단위 테스트 커버리지 90%+
- [ ] Testnet 배포 스크립트
- [ ] Python issuer service
- [ ] End-to-end 통합 테스트 통과
- [ ] Gas benchmark 리포트
- [ ] 서울 아파트 10,000건 attestation 발행 완료 (Testnet)
- [ ] 개발자 문서 (README + API reference)

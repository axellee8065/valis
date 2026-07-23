/// AppraisalAttestation objects (docs/05 §3.4).
/// Owned objects — the issuer mints, then transfers to a subscriber or
/// publishes to the shared oracle feed.
module valis::attestation {
    use std::string::{Self, String};
    use sui::clock::Clock;
    use sui::event;
    use valis::errors;
    use valis::property_registry::Property;

    const METHOD_AVM: u8 = 0;
    const METHOD_CONSENSUS: u8 = 1;
    const METHOD_HYBRID: u8 = 2;

    public struct AppraisalAttestation has key, store {
        id: UID,
        property_id: ID,
        property_global_id: vector<u8>,
        value_usd_cents: u64,
        ci_lower_usd_cents: u64,
        ci_upper_usd_cents: u64,
        confidence_bps: u16, // 0-10000
        method: u8,          // 0:AVM 1:CONSENSUS 2:HYBRID
        model_id: String,
        report_uri: String,  // walrus:// | ipfs:// | https://
        report_hash: vector<u8>, // 32 bytes sha256
        issued_at: u64,
        expires_at: u64,
        issuer: address,
        is_revoked: bool,
    }

    /// Capability held by the protocol's issuer service.
    public struct IssuerCap has key, store {
        id: UID,
        allowed_methods: vector<u8>,
    }

    // === Events ===
    public struct AttestationIssued has copy, drop {
        attestation_id: ID,
        property_id: ID,
        property_global_id: vector<u8>,
        value_usd_cents: u64,
        confidence_bps: u16,
        method: u8,
        model_id: String,
    }

    public struct AttestationRevoked has copy, drop {
        attestation_id: ID,
        reason: String,
    }

    // === Init: deployer gets an IssuerCap allowing AVM + HYBRID ===
    fun init(ctx: &mut TxContext) {
        let cap = IssuerCap {
            id: object::new(ctx),
            allowed_methods: vector[METHOD_AVM, METHOD_HYBRID],
        };
        transfer::transfer(cap, ctx.sender());
    }

    // === Entry: mint attestation ===
    public fun issue(
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
        clock: &Clock,
        recipient: address,
        ctx: &mut TxContext,
    ) {
        let att = mint(
            cap,
            property,
            value_usd_cents,
            ci_lower_usd_cents,
            ci_upper_usd_cents,
            confidence_bps,
            method,
            model_id,
            report_uri,
            report_hash,
            validity_ms,
            clock,
            ctx,
        );
        transfer::public_transfer(att, recipient);
    }

    /// Package-internal mint returning the object — lets `valis::batch`
    /// register + attest + feed-publish in a single transaction.
    public(package) fun mint(
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
        clock: &Clock,
        ctx: &mut TxContext,
    ): AppraisalAttestation {
        assert!(value_usd_cents > 0, errors::invalid_valuation());
        assert!(ci_lower_usd_cents <= value_usd_cents, errors::invalid_valuation());
        assert!(ci_upper_usd_cents >= value_usd_cents, errors::invalid_valuation());
        assert!(confidence_bps <= 10000, errors::invalid_confidence());
        assert!(report_hash.length() == 32, errors::invalid_valuation());
        assert!(is_method_allowed(cap, method), errors::not_authorized());

        let now = clock.timestamp_ms();
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
            issuer: ctx.sender(),
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

        att
    }

    public fun revoke(
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

    // === Queries (public accessors replace the doc's `attestation_helper`) ===
    public fun value_usd_cents(a: &AppraisalAttestation): u64 { a.value_usd_cents }
    public fun confidence_bps(a: &AppraisalAttestation): u16 { a.confidence_bps }
    public fun property_global_id(a: &AppraisalAttestation): &vector<u8> { &a.property_global_id }
    public fun property_id(a: &AppraisalAttestation): ID { a.property_id }
    public fun expires_at(a: &AppraisalAttestation): u64 { a.expires_at }
    public fun is_revoked(a: &AppraisalAttestation): bool { a.is_revoked }

    public fun is_valid(a: &AppraisalAttestation, clock: &Clock): bool {
        !a.is_revoked && clock.timestamp_ms() < a.expires_at
    }

    fun is_method_allowed(cap: &IssuerCap, method: u8): bool {
        cap.allowed_methods.contains(&method)
    }

    #[test_only]
    public fun issuer_cap_for_testing(ctx: &mut TxContext): IssuerCap {
        IssuerCap {
            id: object::new(ctx),
            allowed_methods: vector[METHOD_AVM, METHOD_HYBRID],
        }
    }
}

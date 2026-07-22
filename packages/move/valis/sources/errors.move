/// Protocol-wide error codes (docs/05 §3.1).
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

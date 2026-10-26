// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Alma registry: role based access control, credential anchoring (single and
/// batch Merkle roots), revocation, consent for disclosure, and an event trail
/// that the AI monitor reads. No personal data is ever stored here, only hashes.
contract AlmaRegistry {
    enum Role { None, PlatformAdmin, UniversityAdmin, Student, Employer, Regulator }

    struct Institution { string name; address admin; bool active; bool flagged; uint64 createdAt; }
    struct Credential { bytes32 hash; uint32 instId; address holder; uint64 issuedAt; bool revoked; }
    struct Batch { uint32 instId; uint32 count; uint64 anchoredAt; bool revoked; }

    mapping(address => Role) public roleOf;
    mapping(address => uint32) public instOfAdmin;
    mapping(address => uint32) public instOfStudent;
    mapping(uint32 => Institution) public institutions;
    uint32 public institutionCount;

    mapping(bytes32 => Credential) public credentials;
    mapping(bytes32 => Batch) public batches;
    mapping(bytes32 => bool) public revokedLeaf;
    mapping(bytes32 => mapping(address => uint64)) public accessUntil;

    address public immutable platformAdmin;

    event RoleGranted(address indexed account, Role role, address indexed by);
    event InstitutionRegistered(uint32 indexed instId, address indexed admin, string name);
    event InstitutionStatus(uint32 indexed instId, bool active, bool flagged, address indexed by, string reason);
    event CredentialIssued(bytes32 indexed hash, uint32 indexed instId, address indexed holder, string cid);
    event CredentialRevoked(bytes32 indexed hash, uint32 indexed instId, address indexed by);
    event BatchAnchored(bytes32 indexed root, uint32 indexed instId, uint32 count, string manifestCid);
    event BatchRevoked(bytes32 indexed root, uint32 indexed instId, address indexed by);
    event LeafRevoked(bytes32 indexed root, bytes32 indexed leaf, uint32 indexed instId);
    event AccessGranted(bytes32 indexed hash, address indexed holder, address indexed verifier, uint64 until);
    event AccessRevoked(bytes32 indexed hash, address indexed holder, address indexed verifier);

    error NotAllowed(Role needed, Role actual);
    error InstitutionInactive();
    error WrongInstitution();
    error AlreadyExists();
    error NotFound();

    constructor() {
        platformAdmin = msg.sender;
        roleOf[msg.sender] = Role.PlatformAdmin;
        emit RoleGranted(msg.sender, Role.PlatformAdmin, msg.sender);
    }

    modifier onlyRole(Role r) {
        if (roleOf[msg.sender] != r) revert NotAllowed(r, roleOf[msg.sender]);
        _;
    }

    modifier activeIssuer() {
        if (roleOf[msg.sender] != Role.UniversityAdmin) revert NotAllowed(Role.UniversityAdmin, roleOf[msg.sender]);
        if (!institutions[instOfAdmin[msg.sender]].active) revert InstitutionInactive();
        _;
    }

    // ---- role management ----
    function registerInstitution(address admin, string calldata name) external onlyRole(Role.PlatformAdmin) returns (uint32 id) {
        if (roleOf[admin] != Role.None) revert AlreadyExists();
        id = ++institutionCount;
        institutions[id] = Institution(name, admin, true, false, uint64(block.timestamp));
        roleOf[admin] = Role.UniversityAdmin;
        instOfAdmin[admin] = id;
        emit InstitutionRegistered(id, admin, name);
        emit RoleGranted(admin, Role.UniversityAdmin, msg.sender);
    }

    function registerStudent(address student) external activeIssuer {
        if (roleOf[student] != Role.None) revert AlreadyExists();
        roleOf[student] = Role.Student;
        instOfStudent[student] = instOfAdmin[msg.sender];
        emit RoleGranted(student, Role.Student, msg.sender);
    }

    function registerEmployer(address employer) external onlyRole(Role.PlatformAdmin) {
        if (roleOf[employer] != Role.None) revert AlreadyExists();
        roleOf[employer] = Role.Employer;
        emit RoleGranted(employer, Role.Employer, msg.sender);
    }

    function registerRegulator(address regulator) external onlyRole(Role.PlatformAdmin) {
        if (roleOf[regulator] != Role.None) revert AlreadyExists();
        roleOf[regulator] = Role.Regulator;
        emit RoleGranted(regulator, Role.Regulator, msg.sender);
    }

    /// Regulators and the platform admin (used for automatic holds by the AI monitor).
    function setInstitutionStatus(uint32 instId, bool active, bool flagged, string calldata reason) external {
        Role r = roleOf[msg.sender];
        if (r != Role.Regulator && r != Role.PlatformAdmin) revert NotAllowed(Role.Regulator, r);
        if (instId == 0 || instId > institutionCount) revert NotFound();
        Institution storage i = institutions[instId];
        i.active = active; i.flagged = flagged;
        emit InstitutionStatus(instId, active, flagged, msg.sender, reason);
    }

    // ---- issuing ----
    function issueCredential(bytes32 hash, address holder, string calldata cid) external activeIssuer {
        _issue(hash, holder, cid);
    }

    /// Same as issueCredential; the name used in the project report (mintCredential).
    function mintCredential(bytes32 hash, address holder, string calldata cid) external activeIssuer {
        _issue(hash, holder, cid);
    }

    function _issue(bytes32 hash, address holder, string calldata cid) internal {
        if (credentials[hash].issuedAt != 0) revert AlreadyExists();
        uint32 inst = instOfAdmin[msg.sender];
        if (roleOf[holder] != Role.Student || instOfStudent[holder] != inst) revert WrongInstitution();
        credentials[hash] = Credential(hash, inst, holder, uint64(block.timestamp), false);
        emit CredentialIssued(hash, inst, holder, cid);
    }

    /// Generic role grant for the two roles that have no institution (employer, regulator).
    function grantRole(address account, Role role) external onlyRole(Role.PlatformAdmin) {
        if (role != Role.Employer && role != Role.Regulator) revert NotAllowed(Role.Employer, role);
        if (roleOf[account] != Role.None) revert AlreadyExists();
        roleOf[account] = role;
        emit RoleGranted(account, role, msg.sender);
    }

    function revokeCredential(bytes32 hash) external activeIssuer {
        Credential storage c = credentials[hash];
        if (c.issuedAt == 0) revert NotFound();
        if (c.instId != instOfAdmin[msg.sender]) revert WrongInstitution();
        c.revoked = true;
        emit CredentialRevoked(hash, c.instId, msg.sender);
    }

    /// One transaction anchors any number of credentials (scalability).
    function anchorBatch(bytes32 root, uint32 count, string calldata manifestCid) external activeIssuer {
        if (batches[root].anchoredAt != 0) revert AlreadyExists();
        uint32 inst = instOfAdmin[msg.sender];
        batches[root] = Batch(inst, count, uint64(block.timestamp), false);
        emit BatchAnchored(root, inst, count, manifestCid);
    }

    function revokeBatch(bytes32 root) external activeIssuer {
        Batch storage b = batches[root];
        if (b.anchoredAt == 0) revert NotFound();
        if (b.instId != instOfAdmin[msg.sender]) revert WrongInstitution();
        b.revoked = true;
        emit BatchRevoked(root, b.instId, msg.sender);
    }

    function revokeLeaf(bytes32 root, bytes32 leaf) external activeIssuer {
        Batch storage b = batches[root];
        if (b.anchoredAt == 0) revert NotFound();
        if (b.instId != instOfAdmin[msg.sender]) revert WrongInstitution();
        revokedLeaf[leaf] = true;
        emit LeafRevoked(root, leaf, b.instId);
    }

    // ---- consent ----
    function grantAccess(bytes32 hash, address verifier, uint64 until) external onlyRole(Role.Student) {
        if (roleOf[verifier] != Role.Employer) revert NotAllowed(Role.Employer, roleOf[verifier]);
        accessUntil[hash][verifier] = until;
        emit AccessGranted(hash, msg.sender, verifier, until);
    }

    function revokeAccess(bytes32 hash, address verifier) external onlyRole(Role.Student) {
        accessUntil[hash][verifier] = 0;
        emit AccessRevoked(hash, msg.sender, verifier);
    }

    // ---- reads ----
    function hasAccess(bytes32 hash, address verifier) external view returns (bool) {
        return accessUntil[hash][verifier] > block.timestamp;
    }

    function batchStatus(bytes32 root) external view returns (bool exists, bool revoked, uint32 instId, bool issuerActive) {
        Batch storage b = batches[root];
        exists = b.anchoredAt != 0; revoked = b.revoked; instId = b.instId; issuerActive = institutions[b.instId].active;
    }

    /// One call answer for single credentials: true only if issued, not revoked and the issuer is active.
    function verifyCredential(bytes32 hash) external view returns (bool) {
        Credential storage c = credentials[hash];
        return c.issuedAt != 0 && !c.revoked && institutions[c.instId].active;
    }

    function credentialStatus(bytes32 hash) external view returns (bool exists, bool revoked, uint32 instId, address holder, bool issuerActive) {
        Credential storage c = credentials[hash];
        exists = c.issuedAt != 0; revoked = c.revoked; instId = c.instId; holder = c.holder; issuerActive = institutions[c.instId].active;
    }
}

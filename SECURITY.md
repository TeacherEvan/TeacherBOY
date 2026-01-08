# Security Policy

## Supported Versions

We take security seriously and actively maintain security updates for the following versions:

| Version | Supported          | Security Updates |
| ------- | ------------------ | ----------------- |
| 3.5.x   | ✅ Active support  | ✅ Full support   |
| 3.4.x   | ✅ Maintenance     | ✅ Critical fixes |
| < 3.4   | ❌ End of life     | ❌ No support     |

## Reporting a Vulnerability

**⚠️ IMPORTANT: Do not report security vulnerabilities through public GitHub issues.**

### How to Report

1. **Email the maintainers** directly at the project's security contact (see repository settings)
2. **Provide detailed information** including:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes
3. **Allow time for investigation** - we will acknowledge receipt within 48 hours
4. **Keep confidential** until a fix is released

### What to Expect

- **Initial response**: Within 48 hours acknowledging your report
- **Regular updates**: Progress updates every 7 days during investigation
- **Fix timeline**: Critical vulnerabilities addressed within 30 days
- **Credit**: Recognition in the security advisory (if desired)

### Scope

This security policy applies to:
- ✅ The Zeus bot core application
- ✅ All included services and agents
- ✅ Official Docker images
- ✅ Documentation and configuration examples

Out of scope:
- ❌ Third-party dependencies (report to upstream)
- ❌ Operating system vulnerabilities
- ❌ Network infrastructure not controlled by the application

---

## Security Features

### Data Privacy & Protection

#### Image Handling Security

**Immediate Memory Cleanup:**
- Images are deleted from memory immediately after processing
- No persistent storage of image data
- Base64 encoded data cleared after vision API calls
- Session timeouts prevent data accumulation

**Privacy Guarantees:**
- ❌ No image files written to disk
- ❌ No image data stored in databases
- ❌ No image backups or logs retained
- ✅ Memory-only processing with immediate cleanup

#### API Key Security

**Environment Variable Requirements:**
```env
# Required - keep secure
LINE_CHANNEL_SECRET=your_secret_here
LINE_CHANNEL_ACCESS_TOKEN=your_token_here

# Optional but recommended - encrypt in production
OPENROUTER_API_KEY=your_key_here
BRAVE_SEARCH_API_KEY=your_key_here
GOOGLE_TRANSLATE_API_KEY=your_key_here
```

**Best Practices:**
- Use environment variables, never hardcode keys
- Rotate API keys regularly
- Use different keys for development/production
- Monitor API key usage for anomalies

#### User Data Protection

**LINE User ID Handling:**
- User IDs are used only for authorization and rate limiting
- No personal information stored beyond LINE user IDs
- Session data automatically expires
- No user data shared with third parties

**Conversation Memory:**
- Optional feature with explicit user consent
- Data stored locally or on user-controlled Hugging Face repos
- Automatic cleanup after configurable TTL
- Encryption available for sensitive deployments

### Access Control

#### Admin & Moderator System

**Role-Based Access:**
- **Admins**: Full system access, unlimited operations
- **Moderators**: Enhanced permissions for content management
- **Regular users**: Standard rate-limited access

**Configuration:**
```env
ADMIN_USER_IDS=U1234567890,U0987654321
MODERATOR_USER_IDS=U111122223333
```

#### Rate Limiting

**Built-in Protection:**
- Translation: 10 requests/minute (standard), unlimited (admin)
- News: 1 request/hour (friends), unlimited (admin/moderator)
- AI features: Admin-only in groups, DM-only for others
- Image analysis: 5 analyses/hour, unlimited (admin)

**Automatic Mitigation:**
- Prevents abuse and resource exhaustion
- Graduated response (warning → temporary block)
- Admin override capability

### Network Security

#### HTTPS Enforcement

**LINE Platform Requirements:**
- All webhooks use HTTPS (enforced by LINE)
- SSL/TLS certificates required for production
- No plaintext HTTP endpoints

#### API Communication

**Secure External APIs:**
- All external API calls use HTTPS
- Certificate validation enabled
- Timeout protection against hanging requests
- Retry logic with exponential backoff

### Operational Security

#### Logging Security

**Safe Logging Practices:**
- No sensitive data in application logs
- API keys never logged
- User messages sanitized before logging
- Error messages don't expose system internals

**Optional Encrypted Logging:**
```env
HISTORY_LOG_ENCRYPTION_KEY=your_32_char_key
```

#### Error Handling

**Secure Error Responses:**
- Generic error messages to users
- Detailed errors only in debug mode
- No stack traces exposed to end users
- Graceful degradation on failures

### Container Security

#### Docker Best Practices

**Security Hardening:**
```dockerfile
# Use official base images
FROM python:3.12-slim

# Run as non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

# Minimal attack surface
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
```

**Runtime Security:**
- No privileged containers
- Read-only filesystem where possible
- Minimal Linux capabilities
- Regular base image updates

---

## Security Checklist for Contributors

### Before Committing Code

- [ ] **No hardcoded secrets** - API keys, passwords, tokens
- [ ] **Input validation** - All user inputs validated and sanitized
- [ ] **Error handling** - No sensitive information in error messages
- [ ] **Logging review** - No sensitive data logged
- [ ] **Dependencies checked** - No vulnerable packages used

### Code Review Security Checklist

- [ ] **Authentication** - Proper access controls implemented
- [ ] **Authorization** - Role-based permissions correct
- [ ] **Data validation** - Input sanitization and type checking
- [ ] **Cryptography** - Secure random generation, proper key handling
- [ ] **Session management** - Secure session handling and timeouts
- [ ] **File handling** - Safe file operations, no path traversal
- [ ] **SQL injection** - Parameterized queries (if applicable)
- [ ] **XSS prevention** - Output encoding for user content

---

## Known Security Considerations

### Third-Party Dependencies

**Regular Updates Required:**
- Monitor for security advisories in dependencies
- Update dependencies promptly when vulnerabilities found
- Use tools like `safety` or `pip-audit` for vulnerability scanning

**Current Dependencies:**
- `fastapi` - Web framework
- `line-bot-sdk` - LINE integration
- `openai` - AI services
- `cryptography` - Encryption support

### External API Risks

**API Security:**
- API keys stored securely in environment variables
- Rate limiting implemented to prevent abuse
- Error handling for API failures
- Fallback mechanisms for service outages

### Data Storage

**Minimal Data Retention:**
- No persistent user data storage
- Temporary session data with automatic cleanup
- Optional encrypted logging for audit trails
- Cloud storage only when explicitly configured by users

---

## Incident Response

### Security Incident Process

1. **Detection**: Monitor for unusual activity or reports
2. **Assessment**: Evaluate impact and scope
3. **Containment**: Isolate affected systems
4. **Recovery**: Restore normal operations
5. **Lessons Learned**: Update security measures

### Contact Information

**Security Issues:** Contact maintainers through repository security advisories

**General Support:** Use GitHub Issues for non-security concerns

---

## Security Updates

### Recent Security Improvements

#### Version 3.5.0 (Latest)
- ✅ **Image Privacy Enhancement**: Immediate memory cleanup after processing
- ✅ **Enhanced Rate Limiting**: Per-user rate limits with admin exemptions
- ✅ **API Key Security**: Environment variable validation
- ✅ **Logging Security**: Sensitive data filtering

#### Version 3.4.0
- ✅ **Incomplete Sentence Protection**: Prevents translation hallucination
- ✅ **Session Security**: Automatic session cleanup and timeouts
- ✅ **Error Handling**: Secure error messages without information disclosure

### Security Roadmap

**Planned Improvements:**
- 🔄 **API Key Rotation**: Automated key rotation system
- 🔄 **Audit Logging**: Comprehensive security event logging
- 🔄 **Dependency Scanning**: Automated vulnerability detection in CI/CD
- 🔄 **Container Scanning**: Security scanning of Docker images

---

## Compliance

### GDPR/CCPA Compliance

**Data Minimization:**
- Only LINE user IDs stored for functionality
- No personal information collected or stored
- User data deleted upon request
- Transparent data handling practices

**User Rights:**
- Right to access stored data
- Right to data deletion
- Right to data portability
- Consent-based features (conversation memory)

### Industry Standards

**Following Best Practices:**
- OWASP guidelines for web application security
- Docker security best practices
- Python security recommendations
- LINE Platform security requirements

---

## Resources

### Security Tools

**Recommended Tools:**
- `bandit` - Python security linter
- `safety` - Dependency vulnerability scanner
- `pip-audit` - Alternative dependency scanner
- `trivy` - Container security scanner

### Learning Resources

**Security Education:**
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [LINE Platform Security](https://developers.line.biz/en/docs/messaging-api/security/)
- [Python Security Best Practices](https://bestpractices.coreinfrastructure.org/en/projects/2234)
- [Docker Security](https://docs.docker.com/develop/dev-best-practices/security/)

### Security Advisories

**Stay Informed:**
- [GitHub Security Advisories](https://github.com/your-repo/security/advisories)
- [LINE Developer Security](https://developers.line.biz/en/docs/messaging-api/security/)
- [Python Security Announcements](https://www.python.org/security/)
- [OpenRouter Security](https://openrouter.ai/docs/security)

---

**Last Updated:** 2026-01-08
**Version:** 1.0.0
**Contact:** Repository maintainers
**Policy Review:** Annual (January)
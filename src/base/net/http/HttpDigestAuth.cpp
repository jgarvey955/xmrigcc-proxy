/* SPDX-License-Identifier: GPL-3.0-or-later */

#include "base/net/http/HttpDigestAuth.h"

#include <algorithm>
#include <cctype>
#include <map>

#ifdef XMRIG_FEATURE_TLS
#   include <openssl/evp.h>
#   include <openssl/rand.h>

namespace {

std::string lower(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return std::tolower(c); });
    return value;
}

bool parseChallenge(const std::string &challenge, std::map<std::string, std::string> &fields)
{
    if (challenge.size() < 7 || lower(challenge.substr(0, 7)) != "digest ") {
        return false;
    }

    size_t pos = 7;
    auto whitespace = [&]() {
        while (pos < challenge.size() && (challenge[pos] == ' ' || challenge[pos] == '\t')) { ++pos; }
    };

    while (pos < challenge.size()) {
        whitespace();
        const size_t start = pos;
        while (pos < challenge.size() && (std::isalnum(static_cast<unsigned char>(challenge[pos])) || challenge[pos] == '-')) { ++pos; }
        const std::string key = lower(challenge.substr(start, pos - start));
        whitespace();
        if (key.empty() || pos == challenge.size() || challenge[pos++] != '=') {
            return false;
        }
        whitespace();

        std::string value;
        if (pos < challenge.size() && challenge[pos] == '"') {
            ++pos;
            bool closed = false;
            while (pos < challenge.size()) {
                char c = challenge[pos++];
                if (c == '"') { closed = true; break; }
                if (c == '\\') {
                    if (pos == challenge.size()) { return false; }
                    c = challenge[pos++];
                }
                if (static_cast<unsigned char>(c) < 32 || c == 127) { return false; }
                value += c;
            }
            if (!closed) { return false; }
        }
        else {
            const size_t begin = pos;
            while (pos < challenge.size() && challenge[pos] != ',' && challenge[pos] != ' ' && challenge[pos] != '\t') {
                if (static_cast<unsigned char>(challenge[pos]) < 32 || challenge[pos] == 127) { return false; }
                ++pos;
            }
            value = challenge.substr(begin, pos - begin);
            if (value.empty()) { return false; }
        }

        if (!fields.emplace(key, value).second) { return false; }
        whitespace();
        if (pos < challenge.size() && (challenge[pos++] != ',' || pos == challenge.size())) { return false; }
    }
    return fields.count("realm") && fields.count("nonce") && !fields.at("nonce").empty();
}

std::string quoted(const std::string &value)
{
    std::string result = "\"";
    for (const char c : value) {
        if (c == '"' || c == '\\') { result += '\\'; }
        result += c;
    }
    return result + '"';
}

std::string hex(const unsigned char *data, size_t size)
{
    static const char digits[] = "0123456789abcdef";
    std::string result;
    result.reserve(size * 2);
    for (size_t i = 0; i < size; ++i) {
        result += digits[data[i] >> 4];
        result += digits[data[i] & 15];
    }
    return result;
}

bool hasAuthQop(const std::string &qop)
{
    size_t pos = 0;
    while (pos < qop.size()) {
        const size_t end = qop.find(',', pos);
        std::string token = qop.substr(pos, end == std::string::npos ? end : end - pos);
        token.erase(std::remove_if(token.begin(), token.end(), [](unsigned char c) { return c == ' ' || c == '\t'; }), token.end());
        if (lower(token) == "auth") { return true; }
        if (end == std::string::npos) { break; }
        pos = end + 1;
    }
    return false;
}

} // namespace
#endif

bool xmrig::HttpDigestAuth::isValidLogin(const std::string &login)
{
    const size_t separator = login.find(':');
    return separator != std::string::npos && separator != 0 &&
        std::none_of(login.begin(), login.end(), [](unsigned char c) { return c < 32 || c == 127; });
}

std::string xmrig::HttpDigestAuth::authorization(const std::string &challenge, const std::string &login,
                                               const std::string &method, const std::string &uri)
{
#ifdef XMRIG_FEATURE_TLS
    std::map<std::string, std::string> fields;
    if (!isValidLogin(login) || !parseChallenge(challenge, fields)) { return {}; }

    const std::string algorithm = fields.count("algorithm") ? lower(fields.at("algorithm")) : "md5";
    const bool session = algorithm == "md5-sess" || algorithm == "sha-256-sess";
    const EVP_MD *digest = nullptr;
    if (algorithm == "md5" || algorithm == "md5-sess") { digest = EVP_md5(); }
    else if (algorithm == "sha-256" || algorithm == "sha-256-sess") { digest = EVP_sha256(); }
    else { return {}; }

    const bool qop = fields.count("qop") != 0;
    if (qop && !hasAuthQop(fields.at("qop"))) { return {}; }
    if (fields.count("userhash") && lower(fields.at("userhash")) == "true") { return {}; }

    bool hashOk = true;
    auto hash = [&](const std::string &value) {
        unsigned char bytes[EVP_MAX_MD_SIZE];
        unsigned int size = 0;
        if (EVP_Digest(value.data(), value.size(), bytes, &size, digest, nullptr) != 1) {
            hashOk = false;
            return std::string();
        }
        return hex(bytes, size);
    };

    unsigned char random[16];
    if (RAND_bytes(random, sizeof(random)) != 1) { return {}; }
    const std::string cnonce = hex(random, sizeof(random));
    const size_t separator = login.find(':');
    const std::string username = login.substr(0, separator);
    const std::string realm = fields.at("realm");
    const std::string nonce = fields.at("nonce");
    std::string a1 = hash(username + ':' + realm + ':' + login.substr(separator + 1));
    if (session) { a1 = hash(a1 + ':' + nonce + ':' + cnonce); }
    const std::string a2 = hash(method + ':' + uri);
    const std::string response = hash(a1 + ':' + nonce + (qop ? ":00000001:" + cnonce + ":auth:" : ":") + a2);
    if (!hashOk) { return {}; }

    std::string result = "Digest username=" + quoted(username) + ", realm=" + quoted(realm) +
        ", nonce=" + quoted(nonce) + ", uri=" + quoted(uri) + ", response=" + quoted(response) + ", algorithm=" + algorithm;
    if (qop) { result += ", qop=auth, nc=00000001"; }
    if (qop || session) { result += ", cnonce=" + quoted(cnonce); }
    if (fields.count("opaque")) { result += ", opaque=" + quoted(fields.at("opaque")); }
    return result;
#else
    return {};
#endif
}

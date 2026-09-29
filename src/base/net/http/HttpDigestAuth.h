/* SPDX-License-Identifier: GPL-3.0-or-later */

#ifndef XMRIG_HTTPDIGESTAUTH_H
#define XMRIG_HTTPDIGESTAUTH_H

#include <string>

namespace xmrig {

class HttpDigestAuth
{
public:
    static bool isValidLogin(const std::string &login);
    static std::string authorization(const std::string &challenge, const std::string &login,
                                     const std::string &method, const std::string &uri);
};

} // namespace xmrig

#endif

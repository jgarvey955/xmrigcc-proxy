/* XMRig
 * Copyright 2010      Jeff Garzik <jgarzik@pobox.com>
 * Copyright 2012-2014 pooler      <pooler@litecoinpool.org>
 * Copyright 2014      Lucas Jones <https://github.com/lucasjones>
 * Copyright 2014-2016 Wolf9466    <https://github.com/OhGodAPet>
 * Copyright 2016      Jay D Dee   <jayddee246@gmail.com>
 * Copyright 2017-2018 XMR-Stak    <https://github.com/fireice-uk>, <https://github.com/psychocrypt>
 * Copyright 2018-2019 SChernykh   <https://github.com/SChernykh>
 * Copyright 2016-2019 XMRig       <https://github.com/xmrig>, <support@xmrig.com>
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 *   GNU General Public License for more details.
 *
 *   You should have received a copy of the GNU General Public License
 *   along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef XMRIG_DONATE_H
#define XMRIG_DONATE_H


#include <stdint.h>


/*
 * Dev donation.
 *
 * Donation defaults to 5%. An explicit donate level of 0 disables it; nonzero values below 5% are clamped to 5%.
 *
 * If you plan on changing this setting to 0 please consider making a one off donation to my wallet:
 * XMR: 45ny5y3EYkhF7KzTYbVnC3Zt6MmvszsSxPhdY1kg35GzNFX3BDPqK4gLzxJHqJXwSfC4GSB3cAUVfBj3mACNGZS42QsUQ6F
 *
 * How it works:
 * Upstreams randomly switch to dev pool in range from 50 to 150 minutes, to reduce dev pool peak load.
 * Stays on dev pool at least kDonateLevel minutes.
 * Choice next donation time, with overime compensation. In proxy no way to use precise donation time.
 * You can check actual donation via API.
 *
 * Since 2.15.0
 * If you set level to 0 it will enable donate over proxy feature.
 */
constexpr const int kDefaultDonateLevel = 5;
constexpr const int kMinimumDonateLevel = 5;


#endif /* XMRIG_DONATE_H */

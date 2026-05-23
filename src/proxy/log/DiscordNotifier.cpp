/* XMRig
 * Copyright (c) 2018-2025 SChernykh   <https://github.com/SChernykh>
 * Copyright (c) 2016-2025 XMRig       <https://github.com/xmrig>, <support@xmrig.com>
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 */

#include "proxy/log/DiscordNotifier.h"
#include "3rdparty/rapidjson/document.h"
#include "base/io/json/Json.h"
#include "base/io/log/Log.h"
#include "base/io/log/Tags.h"
#include "base/net/http/Fetch.h"
#include "base/net/http/HttpData.h"
#include "base/tools/Chrono.h"
#include "core/config/Config.h"
#include "core/Controller.h"
#include "proxy/events/AcceptEvent.h"
#include "proxy/Miner.h"
#include "proxy/Stats.h"
#include "proxy/workers/Workers.h"


#include <cinttypes>
#include <cstdio>
#include <cstring>


namespace xmrig {


const char *DiscordConfig::kField = "discord";


static std::string escapeDiscordJson(const std::string &value)
{
    std::string out;
    out.reserve(value.size() + 16);

    for (char c : value) {
        switch (c) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out += c;
            break;
        }
    }

    return out;
}


static void appendLine(std::string &out, const char *key, const char *value)
{
    if (value && strlen(value) > 0) {
        out += "\n";
        out += key;
        out += ": ";
        out += value;
    }
}


} // namespace xmrig


bool xmrig::DiscordConfig::isEnabled() const
{
    return enabled && !webhook.isEmpty();
}


bool xmrig::DiscordConfig::read(const rapidjson::Value &value)
{
    if (!value.IsObject()) {
        return true;
    }

    enabled          = Json::getBool(value, "enabled", enabled);
    notifyAccepted   = Json::getBool(value, "notify-accepted", notifyAccepted);
    notifyRejected   = Json::getBool(value, "notify-rejected", notifyRejected);
    verbose          = Json::getBool(value, "verbose", verbose);
    includeWorker    = Json::getBool(value, "include-worker", includeWorker);
    includeTotals    = Json::getBool(value, "include-totals", includeTotals);
    quiet            = Json::getBool(value, "quiet", quiet);
    acceptedInterval = Json::getUint64(value, "accepted-interval", acceptedInterval);
    minDiff          = Json::getUint64(value, "min-diff", minDiff);
    webhook          = Json::getString(value, "webhook");
    username         = Json::getString(value, "username");
    avatarUrl        = Json::getString(value, "avatar-url");
    mention          = Json::getString(value, "mention");

    return true;
}


rapidjson::Value xmrig::DiscordConfig::toJSON(rapidjson::Document &doc) const
{
    using namespace rapidjson;
    auto &allocator = doc.GetAllocator();

    Value out(kObjectType);
    out.AddMember("enabled", enabled, allocator);
    out.AddMember("webhook", webhook.toJSON(), allocator);
    out.AddMember("notify-accepted", notifyAccepted, allocator);
    out.AddMember("accepted-interval", acceptedInterval, allocator);
    out.AddMember("notify-rejected", notifyRejected, allocator);
    out.AddMember("verbose", verbose, allocator);
    out.AddMember("include-worker", includeWorker, allocator);
    out.AddMember("include-totals", includeTotals, allocator);
    out.AddMember("min-diff", minDiff, allocator);
    out.AddMember("username", username.toJSON(), allocator);
    out.AddMember("avatar-url", avatarUrl.toJSON(), allocator);
    out.AddMember("mention", mention.toJSON(), allocator);
    out.AddMember("quiet", quiet, allocator);

    return out;
}


xmrig::DiscordNotifier::DiscordNotifier(Controller *controller, Stats *stats) :
    m_controller(controller),
    m_stats(stats)
{
    m_httpListener = std::shared_ptr<IHttpListener>(this, [](IHttpListener *) {});
    controller->addListener(this);
}


xmrig::DiscordNotifier::~DiscordNotifier() = default;


void xmrig::DiscordNotifier::onConfigChanged(Config *, Config *)
{
    m_windowAccepted = 0;
    m_windowDiff     = 0;
    m_windowStart    = 0;
}


void xmrig::DiscordNotifier::onEvent(IEvent *event)
{
    if (event->type() == IEvent::AcceptType) {
        accept(static_cast<AcceptEvent *>(event));
    }
}


void xmrig::DiscordNotifier::onHttpData(const HttpData &data)
{
    if (!m_controller->config()->discord().quiet && data.status >= 400) {
        LOG_WARN("%s Discord webhook returned HTTP %d", Tags::proxy(), data.status);
    }
}


void xmrig::DiscordNotifier::onRejectedEvent(IEvent *event)
{
    if (event->type() == IEvent::AcceptType) {
        reject(static_cast<AcceptEvent *>(event));
    }
}


bool xmrig::DiscordNotifier::parseWebhook(WebhookTarget &target) const
{
    const DiscordConfig &config = m_controller->config()->discord();
    const char *url = config.webhook.data();

    if (!url) {
        return false;
    }

    const char *base = nullptr;
    if (strncmp(url, "https://", 8) == 0) {
        target.tls  = true;
        target.port = 443;
        base = url + 8;
    }
    else if (strncmp(url, "http://", 7) == 0) {
        target.tls  = false;
        target.port = 80;
        base = url + 7;
    }
    else {
        return false;
    }

    const char *path = strchr(base, '/');
    if (!path || path == base) {
        return false;
    }

    const char *port = static_cast<const char *>(memchr(base, ':', static_cast<size_t>(path - base)));
    if (port) {
        target.host = String(base, static_cast<size_t>(port - base));
        target.port = static_cast<uint16_t>(strtol(port + 1, nullptr, 10));
    }
    else {
        target.host = String(base, static_cast<size_t>(path - base));
    }

    target.path = path;

    return !target.host.isEmpty() && !target.path.isEmpty() && target.port > 0;
}


const char *xmrig::DiscordNotifier::workerName(const Miner *miner) const
{
    if (!miner) {
        return nullptr;
    }

    switch (m_controller->config()->workersMode()) {
    case Workers::RigID:
        return miner->rigId(true);

    case Workers::User:
        return miner->user();

    case Workers::Password:
        return miner->password();

    case Workers::Agent:
        return miner->agent();

    case Workers::IP:
        return miner->ip();

    default:
        break;
    }

    return nullptr;
}


std::string xmrig::DiscordNotifier::acceptedMessage(const AcceptEvent *event) const
{
    const DiscordConfig &config = m_controller->config()->discord();
    char line[512] = { 0 };
    snprintf(line, sizeof(line) - 1, "Accepted block/share: diff %" PRIu64 ", actual diff %" PRIu64 ", elapsed %" PRIu64 " ms",
             event->result.diff, event->result.actualDiff, event->result.elapsed);

    std::string out = line;
    if (!config.mention.isEmpty()) {
        out = std::string(config.mention.data()) + " " + out;
    }

    if (config.includeWorker) {
        appendLine(out, "Worker", workerName(event->miner()));
    }

    if (config.verbose && event->miner()) {
        appendLine(out, "IP", event->miner()->ip());
        appendLine(out, "User", event->miner()->user());
        appendLine(out, "Rig ID", event->miner()->rigId());
        appendLine(out, "Agent", event->miner()->agent());
    }

    if (config.includeTotals) {
        snprintf(line, sizeof(line) - 1, "\nTotals: accepted %" PRIu64 ", rejected %" PRIu64 ", invalid %" PRIu64,
                 m_stats->data().accepted, m_stats->data().rejected, m_stats->data().invalid);
        out += line;
    }

    return out;
}


std::string xmrig::DiscordNotifier::rejectedMessage(const AcceptEvent *event) const
{
    char line[512] = { 0 };
    snprintf(line, sizeof(line) - 1, "Rejected block/share: diff %" PRIu64 ", elapsed %" PRIu64 " ms, error: %s",
             event->result.diff, event->result.elapsed, event->error() ? event->error() : "unknown");

    std::string out = line;
    if (m_controller->config()->discord().includeWorker) {
        appendLine(out, "Worker", workerName(event->miner()));
    }

    return out;
}


std::string xmrig::DiscordNotifier::summaryMessage(const AcceptEvent *event, uint64_t count, uint64_t seconds) const
{
    const DiscordConfig &config = m_controller->config()->discord();
    char line[512] = { 0 };
    snprintf(line, sizeof(line) - 1, "%" PRIu64 " accepted block/share event%s in %" PRIu64 " seconds. Total diff %" PRIu64,
             count, count == 1 ? "" : "s", seconds, m_windowDiff);

    std::string out = line;
    if (!config.mention.isEmpty()) {
        out = std::string(config.mention.data()) + " " + out;
    }

    if (config.includeWorker && event) {
        appendLine(out, "Last worker", workerName(event->miner()));
    }

    if (config.includeTotals) {
        snprintf(line, sizeof(line) - 1, "\nTotals: accepted %" PRIu64 ", rejected %" PRIu64 ", invalid %" PRIu64,
                 m_stats->data().accepted, m_stats->data().rejected, m_stats->data().invalid);
        out += line;
    }

    return out;
}


void xmrig::DiscordNotifier::accept(const AcceptEvent *event)
{
    const DiscordConfig &config = m_controller->config()->discord();
    if (!config.isEnabled() || !config.notifyAccepted || event->isDonate() || event->isCustomDiff() || event->result.diff < config.minDiff) {
        return;
    }

    if (config.acceptedInterval == 0) {
        send(acceptedMessage(event));
        return;
    }

    const uint64_t now = Chrono::steadyMSecs() / 1000;
    if (m_windowStart == 0) {
        m_windowStart = now;
    }

    m_windowAccepted++;
    m_windowDiff += event->result.diff;

    if (now - m_windowStart >= config.acceptedInterval) {
        flushSummary(event, now);
    }
}


void xmrig::DiscordNotifier::flushSummary(const AcceptEvent *event, uint64_t now)
{
    if (m_windowAccepted > 0) {
        send(summaryMessage(event, m_windowAccepted, now - m_windowStart));
    }

    m_windowAccepted = 0;
    m_windowDiff     = 0;
    m_windowStart    = now;
}


void xmrig::DiscordNotifier::reject(const AcceptEvent *event)
{
    const DiscordConfig &config = m_controller->config()->discord();
    if (!config.isEnabled() || !config.notifyRejected || event->isDonate()) {
        return;
    }

    send(rejectedMessage(event));
}


void xmrig::DiscordNotifier::send(const std::string &content) const
{
    WebhookTarget target;
    if (!parseWebhook(target)) {
        if (!m_controller->config()->discord().quiet) {
            LOG_WARN("%s invalid Discord webhook URL", Tags::proxy());
        }

        return;
    }

    const DiscordConfig &config = m_controller->config()->discord();
    std::string body = "{\"content\":\"" + escapeDiscordJson(content) + "\"";

    if (!config.username.isEmpty()) {
        body += ",\"username\":\"" + escapeDiscordJson(config.username.data()) + "\"";
    }

    if (!config.avatarUrl.isEmpty()) {
        body += ",\"avatar_url\":\"" + escapeDiscordJson(config.avatarUrl.data()) + "\"";
    }

    body += "}";

    FetchRequest req(HTTP_POST, target.host, target.port, target.path, target.tls, config.quiet, body.c_str(), body.size(), HttpData::kApplicationJson.c_str());
    req.timeout = 10000;

    fetch(Tags::proxy(), std::move(req), m_httpListener);
}

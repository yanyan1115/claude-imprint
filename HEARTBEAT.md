# Heartbeat Checklist

## Behavior Rules
- Check the checklist below, execute items as needed
- If nothing to do, return HEARTBEAT_OK
- Send notifications via Telegram to your configured chat_id
- Respect quiet hours (configurable, default 23:00-07:00) — no messages unless urgent
- Keep messages concise — don't over-explain

When the heartbeat agent wakes up, check the following items in order.

## Morning Briefing (07:00-09:00 in your timezone)
If current time is between 07:00-09:00 and no morning message sent today,
send a morning briefing via Telegram:

Example format:
```
🌅 Good morning!

📅 Today is Saturday, March 22
🌤️ Weather: Partly cloudy, 18°C

Let me know if you need anything!
```

Mark as notified after sending. Don't repeat today.

## Routine Checks
- [ ] If more than 1 hour since last heartbeat, check for active tasks in memory

## Custom Monitors
<!-- Add your own monitoring items here -->
<!-- Format: - [ ] Description | How to check | When to notify -->

## Notification Channels
- **Telegram**: Primary channel, use reply tool (configure your chat_id)

## Rules
- Quiet hours (23:00-07:00): no proactive messages unless urgent
- Don't send duplicate notifications (check memory first)
- Batch multiple notifications into one message, don't spam
- Morning briefing: once per day only

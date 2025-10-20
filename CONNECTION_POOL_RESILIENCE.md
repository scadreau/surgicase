# Connection Pool Resilience Enhancement

**Date:** October 20, 2025  
**Enhancement:** Preserve authenticated connections during AWS Secrets Manager outages

---

## The Insight

Database connections that are already authenticated will continue working even when:
- AWS Secrets Manager is down
- We can't refresh credentials
- Credentials have rotated (existing connections remain valid)

**Why?** Once a MySQL/Aurora connection is established and authenticated, the database doesn't re-check credentials. The connection stays authenticated until closed.

---

## The Problem (Before)

During AWS Secrets Manager outages:

1. **Secrets fail to refresh** → We use stale cached credentials ✅
2. **Existing connections work** → But get closed by cleanup job ❌
3. **New connections needed** → Try to use stale cache credentials ✅
4. **But pool is empty** → Because we closed working connections! ❌

**Result:** Unnecessary connection churn and potential failures

---

## The Solution (Now)

### Smart Connection Lifetime Management

The system now tracks Secrets Manager health and automatically adjusts connection pool behavior:

#### Normal Operations
- **Max Idle Time:** 1 hour (connections unused for 1h get closed)
- **Max Lifetime:** 4 hours (connections older than 4h get closed)
- **Behavior:** Normal aggressive cleanup to prevent stale connections

#### During AWS Secrets Manager Outages
- **Max Idle Time:** 2 hours (extended 2x)
- **Max Lifetime:** 8 hours (extended 2x)
- **Behavior:** Preserve authenticated connections that continue to work
- **Logging:** "🛡️ Secrets Manager degraded - extending connection lifetimes"

---

## How It Works

### 1. Health Tracking

**File:** `core/database.py`

```python
# Global tracking
_secrets_health = {
    "last_success": time.time(),
    "consecutive_failures": 0
}
```

Every time we fetch database credentials:
- **Success:** Updates `last_success` timestamp, resets failure count
- **Failure:** Increments failure count (but uses stale cache)

### 2. Adaptive Cleanup

**Function:** `cleanup_stale_connections()`

```python
# Check if secrets manager is having issues
time_since_last_success = current_time - _secrets_health["last_success"]
secrets_degraded = time_since_last_success > 3600  # 1+ hour without refresh

# During secrets issues, extend connection lifetimes 2x
if secrets_degraded:
    max_idle = max_idle * 2      # 1h → 2h
    max_lifetime = max_lifetime * 2  # 4h → 8h
```

### 3. Scheduler Integration

**File:** `utils/scheduler.py`

The hourly pool cleanup job now logs when in resilience mode:

```python
if result.get("secrets_degraded"):
    logger.warning("🛡️ Pool cleanup running in resilience mode - extended connection lifetimes")
```

---

## Benefits

### 1. **Fewer Connection Errors**
- Existing authenticated connections preserved
- Less connection churn during AWS outages
- Smoother degraded mode operation

### 2. **Better Resource Utilization**
- Don't close working connections unnecessarily
- Reduce database load during incidents
- Maintain connection pool depth

### 3. **Automatic Recovery**
- System automatically detects when Secrets Manager recovers
- Returns to normal connection lifetimes
- No manual intervention needed

### 4. **Transparent to Application**
- No code changes needed in endpoints
- Automatic protection for all database operations
- Backward compatible

---

## Example Scenario

### AWS Secrets Manager Outage

**08:12 UTC** - AWS Secrets Manager outage begins
```
⚠️ AWS Secrets Manager error - using stale cache
🛡️ Connection pool: Using authenticated connections (age: 1.5h)
```

**09:00 UTC** - Hourly pool cleanup runs
```
🛡️ Pool cleanup running in resilience mode - extended connection lifetimes
   Max idle: 2.0h (extended), Max lifetime: 8.0h (extended)
✅ Pool cleanup completed: removed 0 stale connections
   Keeping 47 working connections alive
```

**10:00 UTC** - Second cleanup during outage
```
🛡️ Pool cleanup running in resilience mode
✅ Removed 5 very old connections (>8h lifetime)
   Keeping 42 working connections alive
```

**11:30 UTC** - AWS Secrets Manager recovers
```
✅ Secrets warming completed: 9 secrets refreshed
✅ Secrets Manager health restored
```

**12:00 UTC** - Cleanup after recovery
```
✅ Pool cleanup completed: removed 8 stale connections
   Normal lifetimes restored (idle: 1h, lifetime: 4h)
   Pool has 34 fresh connections
```

---

## Monitoring

### Log Messages

**Normal Operations:**
```
✅ Pool cleanup completed: no stale connections found
```

**Resilience Mode Active:**
```
🛡️ Secrets Manager degraded - extending connection lifetimes (idle: 2.0h, lifetime: 8.0h)
🛡️ Pool cleanup running in resilience mode
```

**Recovery:**
```
✅ Secrets warming completed: 9 secrets refreshed
✅ Pool cleanup completed (normal lifetimes restored)
```

### Pool Stats

The `get_pool_stats()` function returns:
```python
{
    "pool_size": 47,
    "secrets_degraded": True,  # NEW
    "extended_lifetimes": True, # NEW
    "avg_connection_age": 5400,
    "max_connection_age": 7200
}
```

---

## Configuration

### Current Settings

**Normal Mode:**
- `max_idle_time`: 3,600 seconds (1 hour)
- `max_lifetime`: 14,400 seconds (4 hours)

**Resilience Mode (Auto-activated):**
- `max_idle_time`: 7,200 seconds (2 hours)
- `max_lifetime`: 28,800 seconds (8 hours)

**Trigger:**
- Activates when no successful secrets refresh for 1+ hour
- Deactivates automatically when secrets refresh succeeds

### Tuning (if needed)

To adjust resilience mode multiplier, edit `core/database.py`:

```python
# Current: 2x extension
if secrets_degraded:
    max_idle = max_idle * 2
    max_lifetime = max_lifetime * 2

# To be more aggressive (3x):
if secrets_degraded:
    max_idle = max_idle * 3
    max_lifetime = max_lifetime * 3
```

---

## Technical Details

### Why This Works

1. **MySQL/Aurora Connection Authentication:**
   - Authentication happens once at connection establishment
   - Server doesn't re-validate credentials on existing connections
   - Connection remains valid until explicitly closed

2. **Credential Rotation:**
   - New credentials take effect for NEW connections only
   - Existing connections continue with old credentials
   - Grace period allows smooth transition

3. **Stale Cache + Authenticated Connections:**
   - During AWS outage: Can't get new credentials
   - Stale cache: Has old (but recently valid) credentials
   - New connections: Use stale cache (may work if rotation hasn't happened)
   - Existing connections: Already authenticated (always work)

### Edge Cases Handled

**Case 1: Credential Rotation During AWS Outage**
- Existing connections: ✅ Continue working
- New connections with stale cache: ❌ May fail with "Access denied"
- Auto-recovery: Kicks in, clears cache, retries
- System handles gracefully

**Case 2: Very Long AWS Outage (>8 hours)**
- Connections eventually age out at 8h extended lifetime
- New connections attempted with stale cache
- If credentials rotated: Auto-recovery handles it
- If not rotated: Stale cache still works

**Case 3: Rapid Recovery**
- Secrets Manager comes back quickly (<1 hour)
- Resilience mode never activates
- Normal operation continues

---

## Testing

### Verify Health Tracking

```python
from core.database import _secrets_health
import time

print(f"Last successful refresh: {time.time() - _secrets_health['last_success']:.0f}s ago")
print(f"Consecutive failures: {_secrets_health['consecutive_failures']}")
```

### Simulate Degraded Mode

```python
from core.database import _secrets_health, cleanup_stale_connections
import time

# Simulate 2 hours without successful refresh
_secrets_health['last_success'] = time.time() - 7200

# Run cleanup - should activate resilience mode
result = cleanup_stale_connections()
print(result)
```

### Check Pool Stats

```python
from core.database import get_pool_stats

stats = get_pool_stats()
print(f"Pool size: {stats['pool_size']}")
print(f"Degraded mode: {stats.get('secrets_degraded', False)}")
```

---

## Integration with Other Resilience Features

This enhancement works together with:

1. **Stale Cache Fallback** (`utils/secrets_manager.py`)
   - Provides credentials for new connections
   - Health tracking informs pool management

2. **Job Failure Notifications** (`utils/job_failure_notifier.py`)
   - Alerts sent if secrets warming fails
   - Pool quietly extends lifetimes in background

3. **Graceful Degradation** (Overall)
   - Secrets use stale cache
   - Connections stay alive longer
   - Jobs continue to complete
   - System self-heals

---

## Performance Impact

### Memory
- **Minimal:** Only 2 additional fields per tracking dictionary
- **Overhead:** < 1KB for health tracking

### CPU
- **Negligible:** One timestamp comparison per cleanup
- **Benefit:** Fewer connection creations/destructions

### Database Load
- **Reduced:** Fewer connection establishments during outages
- **Benefit:** Less authentication overhead on database

### Overall
- ✅ **Net Positive:** Better resilience with negligible overhead

---

## Future Enhancements

### Potential Improvements

1. **Gradual Lifetime Extension**
   - Start with 1.5x after 30 min
   - Increase to 2x after 1 hour
   - Increase to 3x after 2 hours

2. **Per-Connection Health Checks**
   - Ping connections before cleanup
   - Keep connections that pass health check
   - More granular than age-based cleanup

3. **Metrics Export**
   - Track time spent in degraded mode
   - Count connections saved
   - Alert on extended degraded mode

4. **Integration with Circuit Breaker**
   - Coordinate with other resilience mechanisms
   - Unified degraded mode across all systems

---

## Summary

**The Enhancement:** Preserve authenticated database connections during AWS Secrets Manager outages by extending connection lifetimes 2x.

**Why It Matters:** Existing connections work fine even when we can't refresh credentials - no need to close them aggressively.

**The Result:** More resilient system that maintains performance during AWS infrastructure issues.

**Status:** ✅ Implemented, tested, production-ready

---

**Questions?** See `RESILIENCE_IMPROVEMENTS.md` for the complete resilience strategy.


<?php
// RestockRadar — admin dashboard. Operator view of what the scrapers are
// finding and how healthy each source is. Read-only summary screen.
declare(strict_types=1);
require __DIR__ . '/db.php';

$pdo = db();

// --- KPIs (kept to a few cheap, indexed aggregates) -------------------- //
$newToday = (int) $pdo->query(
    "SELECT COUNT(*) FROM products WHERE first_seen >= NOW() - INTERVAL 1 DAY"
)->fetchColumn();

$sources = $pdo->query(
    "SELECT COUNT(*) total, SUM(enabled) active FROM sources"
)->fetch();

// Detection lag = how fast a run turns up new items (proxy for speed-to-app).
$avgLag = (int) $pdo->query(
    "SELECT COALESCE(AVG(duration_ms),0) FROM scrape_runs
      WHERE started_at >= NOW() - INTERVAL 1 DAY AND status <> 'error'"
)->fetchColumn();

$errors = (int) $pdo->query(
    "SELECT COUNT(*) FROM scrape_runs
      WHERE started_at >= NOW() - INTERVAL 1 DAY AND status = 'error'"
)->fetchColumn();

// --- latest finds ------------------------------------------------------ //
$finds = $pdo->query(
    "SELECT p.title, p.external_id, p.price, p.currency, p.in_stock,
            p.first_seen, p.last_seen, s.display_name AS source
       FROM products p JOIN sources s ON s.id = p.source_id
   ORDER BY p.first_seen DESC LIMIT 9"
)->fetchAll();

// --- source health (today) -------------------------------------------- //
$health = $pdo->query(
    "SELECT s.display_name, s.last_status, s.last_run_at,
            COALESCE(SUM(r.items_new),0)  AS new_today,
            COALESCE(SUM(r.items_found),0) AS found_today
       FROM sources s
       LEFT JOIN scrape_runs r ON r.source_id = s.id
            AND r.started_at >= CURDATE()
   GROUP BY s.id ORDER BY new_today DESC"
)->fetchAll();

// deterministic colour per source/product for the avatar tiles
function tile_color(string $s): string {
    $palette = ['#5b8def','#22c55e','#f5a623','#a855f7','#2dd4bf','#ef4444','#eab308'];
    return $palette[crc32($s) % count($palette)];
}
function initials(string $s): string {
    $p = preg_split('/[\s\-]+/', trim($s));
    return strtoupper(substr($p[0] ?? '', 0, 1) . substr($p[1] ?? ($p[0][1] ?? ''), 0, 1));
}
?>
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RestockRadar — Admin</title>
<link rel="stylesheet" href="assets/app.css">
</head><body>
<header class="topbar">
  <div class="brand"><span class="dot"></span>RESTOCKRADAR <span class="tag">ADMIN</span></div>
  <nav><a class="active" href="index.php">Dashboard</a><a href="sources.php">Sources</a>
       <a href="products.php">Products</a><a href="alerts.php">Alerts</a></nav>
  <div class="right">
    <span class="live"><span class="pulse"></span>SCRAPERS ACTIVE</span>
    <span><?= date('H:i') ?></span>
  </div>
</header>

<div class="wrap">
  <section class="kpis">
    <div class="kpi"><div class="label">New products (24h)</div>
      <div class="value"><?= number_format($newToday) ?></div>
      <div class="sub up">live feed to mobile app</div></div>
    <div class="kpi"><div class="label">Active sources</div>
      <div class="value"><?= (int)$sources['active'] ?> / <?= (int)$sources['total'] ?></div>
      <div class="sub">monitored continuously</div></div>
    <div class="kpi"><div class="label">Avg detection lag</div>
      <div class="value accent"><?= $avgLag ? round($avgLag/1000,1).'s' : '—' ?></div>
      <div class="sub up">listing → database</div></div>
    <div class="kpi"><div class="label">Errors (24h)</div>
      <div class="value"><?= $errors ?></div>
      <div class="sub <?= $errors ? 'down' : '' ?>">across all runs</div></div>
  </section>

  <div class="grid">
    <div class="panel">
      <h2>Latest finds <span class="count"><?= count($finds) ?> shown</span></h2>
      <table><thead><tr>
        <th>Product</th><th>Source</th><th>Price</th><th>Detected</th><th>Status</th>
      </tr></thead><tbody>
      <?php foreach ($finds as $f):
        $isNew = (time() - strtotime($f['first_seen'])) < 1800; ?>
        <tr>
          <td><div class="prod">
            <div class="thumb" style="background:<?= tile_color($f['title']) ?>"><?= initials($f['title']) ?></div>
            <div><div class="name"><?= htmlspecialchars($f['title']) ?></div>
                 <div class="id">#<?= htmlspecialchars($f['external_id']) ?></div></div>
          </div></td>
          <td class="src"><?= htmlspecialchars($f['source']) ?></td>
          <td class="price"><?= $f['price'] ? '£'.number_format((float)$f['price'],2) : '—' ?></td>
          <td class="when"><?= time_ago($f['first_seen']) ?></td>
          <td><?php if ($isNew): ?><span class="pill new">New</span>
              <?php elseif ($f['in_stock']): ?><span class="pill stock">In stock</span>
              <?php else: ?><span class="pill sold">Sold out</span><?php endif; ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody></table>
    </div>

    <div class="panel">
      <h2>Source health</h2>
      <?php foreach ($health as $h): ?>
        <div class="src-row">
          <div class="ico" style="background:<?= tile_color($h['display_name']) ?>"><?= initials($h['display_name']) ?></div>
          <div class="meta">
            <div class="nm"><?= htmlspecialchars($h['display_name']) ?></div>
            <div class="sb">last run <?= $h['last_run_at'] ? time_ago($h['last_run_at']) : 'never' ?></div>
          </div>
          <div class="items"><b><?= (int)$h['new_today'] ?></b> new<br><?= (int)$h['found_today'] ?> seen</div>
          <div class="status <?= htmlspecialchars($h['last_status']) ?>"><span class="d"></span><?= ucfirst($h['last_status']) ?></div>
        </div>
      <?php endforeach; ?>
    </div>
  </div>
</div>
</body></html>

<?php
// RestockRadar REST API — read-only JSON feed consumed by the mobile app.
//
//   GET /api/products?since=<iso8601>&limit=50   newest finds (cursor-friendly)
//   GET /api/sources                             source list + health
//
// Keyed by a simple API token; pagination is by `first_seen` so the app can
// poll "what's new since my last item" cheaply against idx_products_first_seen.
declare(strict_types=1);

require __DIR__ . '/../admin/db.php';

header('Content-Type: application/json');

function fail(int $code, string $msg): never
{
    http_response_code($code);
    echo json_encode(['error' => $msg]);
    exit;
}

// --- auth -------------------------------------------------------------- //
$token = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (!hash_equals(getenv('API_TOKEN') ?: 'dev-token', $token)) {
    fail(401, 'invalid api key');
}

$route = $_GET['route'] ?? 'products';

if ($route === 'products') {
    $limit = min(100, max(1, (int)($_GET['limit'] ?? 50)));
    $since = $_GET['since'] ?? '1970-01-01 00:00:00';

    $stmt = db()->prepare(
        'SELECT p.external_id, p.title, p.price, p.currency, p.url,
                p.image_url, p.in_stock, p.first_seen, s.display_name AS source
           FROM products p
           JOIN sources s ON s.id = p.source_id
          WHERE p.first_seen > :since
       ORDER BY p.first_seen DESC
          LIMIT :limit'
    );
    $stmt->bindValue(':since', $since);
    $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
    $stmt->execute();
    $rows = $stmt->fetchAll();

    echo json_encode([
        'count'  => count($rows),
        'cursor' => $rows[0]['first_seen'] ?? $since,  // newest, for next poll
        'items'  => $rows,
    ]);
    exit;
}

if ($route === 'sources') {
    $rows = db()->query(
        'SELECT slug, display_name, enabled, last_run_at, last_status
           FROM sources ORDER BY display_name'
    )->fetchAll();
    echo json_encode(['items' => $rows]);
    exit;
}

fail(404, 'unknown route');

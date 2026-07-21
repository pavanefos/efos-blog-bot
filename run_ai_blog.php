<?php
/**
 * EFOS AI Blog Automation - PHP trigger.
 *
 * This is an OPTIONAL helper for users who prefer to drive the pipeline from PHP
 * (e.g. a Laravel Artisan command, a cron, or a scheduled task on the server).
 * The actual intelligence (topic discovery, AI research, SEO writing, image
 * generation, Laravel publishing) lives in the Python package under src/.
 *
 * Why PHP + Python? You said you don't want Node.js / n8n. The website is
 * already Laravel (PHP), so PHP is a natural orchestration surface, while
 * Python is ideal for the AI/HTTP plumbing. This script simply shells out to
 * the Python runner.
 *
 * Usage:
 *   php run_ai_blog.php                # run one publishing cycle now
 *   php run_ai_blog.php --dry-run      # run without publishing
 *   php run_ai_blog.php --test         # test API connections
 *
 * Scheduling (Windows Task Scheduler / cron) should call this daily at the
 * desired time, or you can run `python -m src` directly as a long-lived
 * scheduler.
 */

declare(strict_types=1);

const AUTOMATION_DIR = __DIR__;
const PYTHON_BIN = 'python'; // or 'python3' on Linux

function run_command(array $args): int
{
    $cmd = escapeshellcmd(PYTHON_BIN) . ' -m src ' . implode(' ', array_map('escapeshellarg', $args));
    $full = 'cd ' . escapeshellarg(AUTOMATION_DIR) . ' && ' . $cmd;
    echo ">> Running: {$full}\n";
    $exitCode = 0;
    system($full, $exitCode);
    return $exitCode;
}

$args = array_slice($argv, 1);
if (empty($args)) {
    $args = ['--once'];
}

$code = run_command($args);
exit($code);

// pm2 ecosystem 配置 — pm (Project Management)
module.exports = {
  apps: [
    {
      name: 'pm',
      script: './venv/bin/gunicorn',
      args: ['-w', '2', '-b', '127.0.0.1:8092', '--timeout', '300', '--error-logfile', './pm.err', '--capture-output', 'app:app'],
      cwd: '/Users/nmconline/apps/pm',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      watch: false,
      env: {
        URL_PREFIX: '/pm',
        OBJC_DISABLE_INITIALIZE_FORK_SAFETY: 'YES',
        TZ: 'Asia/Shanghai',
      },
    },
  ],
};

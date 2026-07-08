// pm2 ecosystem 配置 — pm (Project Management)
module.exports = {
  apps: [
    {
      name: 'pm',
      script: './.venv/bin/gunicorn',
      args: ['-w', '2', '-k', 'uvicorn.workers.UvicornWorker', '-b', '127.0.0.1:8092', '--timeout', '300', '--error-logfile', './pm.err', '--capture-output', 'main:app'],
      cwd: '/Users/nmconline/apps/pm',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      watch: false,
      env_file: '/Users/nmconline/apps/pm/.env.prod',
      env: {
        URL_PREFIX: '/pm',
        OBJC_DISABLE_INITIALIZE_FORK_SAFETY: 'YES',
        TZ: 'Asia/Shanghai',
      },
    },
    {
      name: 'pm-bot',
      script: '/Users/nmconline/apps/pm/.venv/bin/python',
      args: ['-m', 'wecom.bot'],
      cwd: '/Users/nmconline/apps/pm',
      interpreter: 'none',
      instances: 1,
      autorestart: true,
      watch: false,
      env_file: '/Users/nmconline/apps/pm/.env.prod',
      env: {
        OBJC_DISABLE_INITIALIZE_FORK_SAFETY: 'YES',
        TZ: 'Asia/Shanghai',
        WECHAT_BOT_ID: 'aibzQIGj08lrFN-Qp9vUaAAL1OrJU_bTlsI',
        WECHAT_BOT_SECRET: 'ikmuNcnYlA7cXe1YRyGVfAPiwCKNrlLk4OnLgw0cTlO'
      },
    },
  ],
};

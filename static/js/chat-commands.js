/**
 * chat-commands.js — 网页聊天的「斜线命令」与「会话话题句柄」管理
 *
 * 从 app.js 抽离，保持一域一文件、高内聚低耦合：
 *   - 命令表 + dispatch：整条精确匹配的无参命令(/new /help)，加命令只加一行。
 *   - 话题句柄(topic)：/new 切出一条与后端 Agno 互不串记忆的新会话，localStorage 持久化。
 *
 * 与 app.js 的边界（依赖注入，见 init）：
 *   本模块不直接引用 app.js 的 DOM 或全局状态，一切经 init 注入的回调完成，
 *   两边因此可各自演进；app.js 只在 sendChat 里调 dispatch() / topic() 两处。
 *
 * 安全：前端只持有 topic 句柄(纯字母数字，不含 uid)，session_id = web-{uid}-{topic}
 *   由后端拼、uid 段取自认证身份，故前端无从借它读到别人的会话记忆。
 *
 * 纯 ES5 + IIFE、无构建：挂到 window.ChatCommands，须在 app.js 之前引入。
 */
window.ChatCommands = (function () {
    'use strict';

    // init 注入的宿主能力；未 init 前为安全占位（命令静默无效，不报错）。
    var _deps = {
        appendMsg:     function () {},                 // (role, text) 渲染一条消息
        resetHistory:  function () {},                 // 清空 app.js 的 chatHistory
        clearMessages: function () {},                 // 清空消息框 DOM
        getUserId:     function () { return null; },   // 取当前用户 id（惰性）
    };

    // 当前话题句柄：'' 表默认会话；非空是 /new 生成的句柄。刷新页面复用(localStorage)。
    var _topic = localStorage.getItem('chatTopic') || '';

    // ── 命令表：一命令一 handler。新增命令只加一行，参照后端 wecom/commands.py ──
    var COMMANDS = {
        '/new':  { fn: _cmdNew,  desc: '开启新话题，忘掉之前的对话记忆' },
        '/help': { fn: _cmdHelp, desc: '列出所有可用命令' },
    };

    /** 注入宿主能力，逐个覆盖对应回调（未传的保持占位）。app.js 加载后调用一次。 */
    function init(deps) {
        if (!deps) return;
        for (var k in _deps) {
            if (typeof deps[k] === 'function') _deps[k] = deps[k];
        }
    }

    /** 当前话题句柄，供 sendChat 放进请求体的 topic 字段。 */
    function topic() {
        return _topic;
    }

    /**
     * 尝试把整条输入当斜线命令执行。
     * @return {boolean} 命中并已处理 -> true(调用方应清空输入并 return)；未命中 -> false。
     */
    function dispatch(msg) {
        var handler = COMMANDS[msg];   // 整条精确匹配，无参命令
        if (!handler) return false;
        handler.fn();
        return true;
    }

    // ── 各命令实现 ──

    function _cmdNew() {
        // 句柄取「时间戳 + 随机」的 36 进制串：纯字母数字、≤32，契合后端 _TOPIC_RE 白名单。
        _topic = Date.now().toString(36) + Math.floor(Math.random() * 1e6).toString(36);
        localStorage.setItem('chatTopic', _topic);
        _deps.resetHistory();
        _deps.clearMessages();
        _deps.appendMsg('ai', '🐟 开了个新话题，之前的都忘光啦～有什么想聊的？');
    }

    function _cmdHelp() {
        var lines = ['可用命令：'];
        for (var name in COMMANDS) {
            lines.push(name + '  —  ' + COMMANDS[name].desc);
        }
        _deps.appendMsg('ai', lines.join('\n'));
    }

    // 只暴露最小接口；命令实现与内部状态私有。
    return {
        init:     init,
        dispatch: dispatch,
        topic:    topic,
    };
})();

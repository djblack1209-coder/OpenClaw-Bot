# Source Generated with Decompyle++
# File: message_mixin.cpython-312.pyc (Python 3.12)

import asyncio
import io
import base64
import json
import logging
import re
from src.bot.globals import chat_router, collab_orchestrator, bot_registry, history_store, metrics, send_long_message, send_as_bot, shared_memory, _pending_trades, CLAUDE_BASE, CLAUDE_KEY, get_stock_quote, execute_trade_via_pipeline, get_trading_pipeline
from src.bot.rate_limiter import rate_limiter
from src.notify_style import format_digest
from src.ocr_service import ocr_image, OcrResult
from src.ocr_router import classify_ocr_scene, OcrScene
from src.ocr_processors import process_financial_scene, process_ecommerce_scene
from src.telegram_markdown import md_to_html
logger = logging.getLogger(__name__)

def _match_chinese_command(text = None):
    '''
    匹配中文自然语言触发词，返回 (action_type, arg) 或 None
    '''
    t = text.strip()
    if re.fullmatch('(开始|帮助|菜单|命令|指令|使用说明)', t):
        return ('start', '')
    if re.fullmatch('(清空|清空对话|重置对话|重置会话)', t):
        return ('clear', '')
    if re.fullmatch('(状态|查看状态|机器人状态)', t):
        return ('status', '')
    if re.fullmatch('(配置|配置状态|当前配置|运行配置)', t):
        return ('config', '')
    if re.fullmatch('(成本|配额|用量|成本状态|配额状态)', t):
        return ('cost', '')
    if re.fullmatch('(上下文|上下文状态)', t):
        return ('context', '')
    if re.fullmatch('(压缩|压缩上下文|整理上下文)', t):
        return ('compact', '')
    if re.fullmatch('(新闻|科技早报|早报)', t):
        return ('news', '')
    if re.fullmatch('(指标|运行指标|监控指标)', t):
        return ('metrics', '')
    if re.fullmatch('(分流|分流规则|路由规则|话题分流|多bot分流|多机器人分流)', t):
        return ('lanes', '')
    if re.search('执行场景|自动化菜单|ops帮助', t):
        return ('ops_help', '')
    if re.search('整理邮箱|邮件整理|邮箱分类', t):
        return ('ops_email', '')
    if re.search('执行简报|行业简报|今日简报', t):
        return ('ops_brief', '')
    if re.search('最重要.{0,2}3件事|任务优先级|今日任务', t):
        return ('ops_task_top', '')
    if re.search('赏金猎人|自动接单|接单机器人|\\bbounty\\b', t, re.IGNORECASE):
        return ('ops_bounty_run', '')
    m_bounty_scan = re.search('(?:扫赏金|扫描赏金|找赏金|赏金扫描)\\s*(.*)', t)
    if m_bounty_scan:
        kw = (m_bounty_scan.group(1) or '').strip()
        return ('ops_bounty_scan', kw)
    if re.fullmatch('(赏金列表|赏金机会|赏金看板)', t):
        return ('ops_bounty_list', '')
    if re.fullmatch('(赏金top|赏金排行|高收益赏金)', t):
        return ('ops_bounty_top', '')
    if re.fullmatch('(开工赚钱|打开赏金机会|开赏金链接)', t):
        return ('ops_bounty_open', '')
    m_tweet_plan = re.search('(?:推文计划|分析推文|推文执行计划)\\s+(.+)', t)
    if m_tweet_plan:
        return ('ops_tweet_plan', m_tweet_plan.group(1).strip())
    m_tweet_run = re.search('(?:执行推文|推文执行|推文赚钱|跟着推文赚钱)\\s+(.+)', t)
    if m_tweet_run:
        return ('ops_tweet_run', m_tweet_run.group(1).strip())
    m_docs_search = re.search('(?:文档检索|文档搜索|搜文档)\\s+(.+)', t)
    if m_docs_search:
        return ('ops_docs_search', m_docs_search.group(1).strip())
    m_docs_index = re.search('(?:建立文档索引|索引文档)\\s*(.*)', t)
    if m_docs_index and re.search('文档', t):
        target = (m_docs_index.group(1) or '.').strip() or '.'
        return ('ops_docs_index', target)
    m_meeting = re.search('(?:会议纪要|总结会议)\\s+(.+)', t)
    if m_meeting:
        return ('ops_meeting', m_meeting.group(1).strip())
    m_content = re.search('(?:社媒选题|内容选题|写作选题)\\s*(.*)', t)
    if m_content and re.search('选题', t):
        keyword = (m_content.group(1) or 'AI').strip() or 'AI'
        return ('ops_content', keyword)
    m_social_plan = re.search('(?:社媒计划|发文计划|今日发什么)\\s*(.*)', t)
    if m_social_plan and re.search('计划|发什么', t):
        return ('social_plan', (m_social_plan.group(1) or '').strip())
    m_social_repost = re.search('(?:双平台改写|改写双平台|改写成双平台|双平台草稿)\\s*(.*)', t)
    if m_social_repost:
        return ('social_repost', (m_social_repost.group(1) or '').strip())
    if re.fullmatch('(数字生命首发|首发包|社媒首发包|数字生命人设首发)', t):
        return ('social_launch', '')
    if re.fullmatch('(当前社媒人设|社媒人设|数字生命人设|当前人设)', t):
        return ('social_persona', '')
    m_topic = re.search('(?:研究|分析|看看|学习)(.+?)(?:题材|方向|内容)', t)
    if m_topic:
        return ('social_topic', m_topic.group(1).strip())
    m_xhs = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到小红书', t)
    if m_xhs:
        return ('social_xhs', m_xhs.group(1).strip())
    m_x = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到(?:x|推特|推文)', t, re.IGNORECASE)
    if m_x:
        return ('social_x', m_x.group(1).strip())
    m_dual = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?(?:双平台|同时发|发到两个平台)', t)
    if m_dual:
        return ('social_post', m_dual.group(1).strip())
    if re.fullmatch('(一键发文|热点发文|热点一键发文|蹭热点发文|自动发文)', t):
        return ('social_hotpost', '')
    m_hotpost = re.search('(?:一键发文|热点发文|蹭热点发文|自动发文)\\s+(.+)', t)
    if m_hotpost:
        return ('social_hotpost', m_hotpost.group(1).strip())
    m_monitor_add = re.search('(?:添加资讯监控|新增资讯监控|监控关键词)\\s+(.+)', t)
    if m_monitor_add:
        return ('ops_monitor_add', m_monitor_add.group(1).strip())
    if re.fullmatch('(资讯监控列表|新闻监控列表)', t):
        return ('ops_monitor_list', '')
    if re.fullmatch('(运行资讯监控|扫描资讯监控|立即扫描资讯监控)', t):
        return ('ops_monitor_run', '')
    m_remind = re.search('(\\d+)\\s*分钟后提醒我\\s+(.+)', t)
    if m_remind:
        return ('ops_life_remind', f'''{m_remind.group(1)}|||{m_remind.group(2).strip()}''')
    m_remind_default = re.search('提醒我\\s+(.+)', t)
    if m_remind_default:
        return ('ops_life_remind', f'''30|||{m_remind_default.group(1).strip()}''')
    m_project = re.search('(?:项目周报|生成项目周报)\\s*(.*)', t)
    if m_project and re.search('项目周报', t):
        target = (m_project.group(1) or '.').strip() or '.'
        return ('ops_project', target)
    m_dev = re.search('(?:开发流程|执行开发流程|跑开发流程)\\s*(.*)', t)
    if m_dev and re.search('开发流程', t):
        target = (m_dev.group(1) or '.').strip() or '.'
        return ('ops_dev', target)
    if re.search('(开始|自动|帮我|一键).{0,2}投资|找.{0,2}机会|自动交易|帮我(赚钱|炒股|交易)|今天买什么|有什么(机会|可以买)', t):
        return ('auto_invest', t)
    if re.search('扫描|扫一下|扫一扫|看看市场|市场扫描|全市场', t):
        return ('scan', '')
    m = re.search('(?:分析|技术分析|看看|研究)\\s*([A-Za-z]{1,5}(?:-USD)?)', t)
    if m:
        return ('ta', m.group(1).upper())
    m = re.search('([A-Za-z]{1,5})\\s*(?:信号|买卖|怎么样|能买吗|能不能买)', t)
    if m:
        return ('signal', m.group(1).upper())
    m = re.search('([A-Za-z]{1,5})\\s*(?:多少钱|股价|价格|行情)', t)
    if m:
        return ('quote', m.group(1).upper())
    m = re.search('(?:查|看).{0,2}(?:行情|价格)\\s*([A-Za-z]{1,5})?', t)
    if m and m.group(1):
        return ('quote', m.group(1).upper())
    if re.search('市场概览|大盘|今天行情|行情怎么样|市场怎么样', t):
        return ('market', '')
    if re.search('我的?(持仓|仓位|组合|资产)|看看(持仓|仓位)|投资组合', t):
        return ('portfolio', '')
    if re.search('(IBKR|盈透|真实|实盘).{0,2}(持仓|仓位)', t):
        return ('positions', '')
    if re.search('绩效|战绩|成绩|表现|胜率|盈亏|收益率|夏普|回撤', t):
        return ('performance', '')
    if re.search('复盘|总结.{0,2}(今天|交易)|回顾|检讨|反思', t):
        return ('review', '')
    if re.search('交易(日志|记录|历史)|日志|看看(记录|日志)', t):
        return ('journal', '')
    if re.search('风控|风险(状态|管理)?|熔断', t):
        return ('risk', '')
    if re.search('持仓监控|监控(状态)?|止损(状态)?|止盈', t):
        return ('monitor', '')
    if re.search('交易系统|系统状态|全部状态', t):
        return ('tradingsystem', '')
    if re.search('启动自动|开启自动|自动交易启动|开始自动', t):
        return ('autotrader_start', '')
    if re.search('停止自动|关闭自动|自动交易停止', t):
        return ('autotrader_stop', '')
    m_bt = re.search('(?:回测|测试策略|backtest)\\s*([A-Za-z\\-]{1,10})?', t)
    if m_bt:
        sym = (m_bt.group(1) or '').strip().upper()
        return ('backtest', sym)
    if re.search('再平衡|调仓|rebalance|配置组合|目标配置', t):
        return ('rebalance', '')
    m = re.search('(?:投资|讨论|分析).{0,2}(?:一下|下)?\\s*(.{2,})', t)
    if m and re.search('投资|讨论', t):
        topic = m.group(1).strip()
        if len(topic) >= 2:
            return ('invest', topic)


class MessageHandlerMixin:
    @staticmethod
    def _is_directed_to_current_bot(text="", chat_type="", username=""):
        if chat_type == "private":
            return True
        if not username:
            return False
        uname = username.strip().lstrip("@").lower()
        if not uname or not text:
            return False
        return f"@{uname}" in text.lower()

    async def _dispatch_chinese_action(self, update = None, context = None, action_type="", action_arg=""):
        """分发中文自然语言命令到对应的命令处理器"""
        if not update or not action_type:
            return

        # 构造 context.args
        context.args = [action_arg] if action_arg else []

        # 命令映射表 — 将 NLP 匹配结果路由到实际命令
        dispatch_map = {
            # ── 基础命令 ──
            "start": self.cmd_start,
            "clear": self.cmd_clear,
            "status": self.cmd_status,
            "config": self.cmd_config,
            "cost": self.cmd_cost,
            "context": self.cmd_context,
            "compact": self.cmd_compact,
            "news": self.cmd_news,
            "metrics": self.cmd_metrics,
            "lanes": self.cmd_lane,
            "memory": self.cmd_memory,
            "settings": self.cmd_settings,
            "draw": self.cmd_draw,
            # ── 执行场景 ──
            "ops_help": self.cmd_ops,
            "ops_brief": self.cmd_brief,
            "hot": self.cmd_hotpost,
            "post": self.cmd_post,
            "social_report": self.cmd_social_report,
            # ── 投资 & 交易 ──
            "invest": self.cmd_invest,
            "auto_invest": self.cmd_invest,
            "quote": self.cmd_quote,
            "market": self.cmd_market,
            "scan": self.cmd_scan,
            "ta": self.cmd_ta,
            "signal": self.cmd_signal,
            "portfolio": self.cmd_portfolio,
            "positions": self.cmd_ipositions,
            "performance": self.cmd_performance,
            "review": self.cmd_review,
            "journal": self.cmd_journal,
            "buy": self.cmd_buy,
            "sell": self.cmd_sell,
            "risk": self.cmd_risk,
            "monitor": self.cmd_monitor,
            "tradingsystem": self.cmd_tradingsystem,
            "backtest": self.cmd_backtest,
            "rebalance": self.cmd_rebalance,
            # ── 社媒 ──
            "social_plan": self.cmd_social_plan,
            "social_repost": self.cmd_social_repost,
            "social_launch": self.cmd_social_launch,
            "social_persona": self.cmd_social_persona,
            "social_topic": self.cmd_topic,
            "social_xhs": self.cmd_xhs,
            "social_x": self.cmd_xpost,
            "social_post": self.cmd_post,
            "social_hotpost": self.cmd_hotpost,
        }

        handler = dispatch_map.get(action_type)
        if handler:
            try:
                await handler(update, context)
            except Exception as e:
                logger.warning("[ChineseNLP] 分发 %s 失败: %s", action_type, e)
            return

        # 带参数的特殊命令
        try:
            if action_type == "ops_email":
                context.args = ["email"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_task_top":
                context.args = ["task", "top"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_run":
                context.args = ["bounty", "run"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_scan":
                context.args = ["bounty", "scan"] + ([action_arg] if action_arg else [])
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_list":
                context.args = ["bounty", "list"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_top":
                context.args = ["bounty", "top"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_open":
                context.args = ["bounty", "open"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_tweet_plan":
                context.args = ["tweet", "plan", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_tweet_run":
                context.args = ["tweet", "run", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_docs_search":
                context.args = ["docs", "search", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_docs_index":
                context.args = ["docs", "index", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_meeting":
                context.args = ["meeting", action_arg] if action_arg else ["meeting"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_content":
                context.args = ["content", action_arg] if action_arg else ["content"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_add":
                context.args = ["monitor", "add", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_list":
                context.args = ["monitor", "list"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_run":
                context.args = ["monitor", "run"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_life_remind":
                # action_arg format: "minutes|||message"
                parts = action_arg.split("|||", 1) if action_arg else []
                if len(parts) == 2:
                    context.args = ["life", "remind", parts[0], parts[1]]
                else:
                    context.args = ["life", "remind"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_project":
                context.args = ["project", action_arg] if action_arg else ["project"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_dev":
                context.args = ["dev", action_arg] if action_arg else ["dev"]
                await self.cmd_ops(update, context)
            elif action_type == "autotrader_start":
                context.args = ["start"]
                await self.cmd_autotrader(update, context)
            elif action_type == "autotrader_stop":
                context.args = ["stop"]
                await self.cmd_autotrader(update, context)
        except Exception as e:
            logger.warning("[ChineseNLP] 分发 %s(%s) 失败: %s", action_type, action_arg, e)

    
    def _pick_workflow_bot(self, candidates=None, exclude=None):
        exclude_set = set(exclude or [])
        if candidates:
            for bot_id in candidates:
                if bot_id in exclude_set:
                    continue
                if bot_id in bot_registry:
                    return candidates, bot_id
        for bot_id in bot_registry:
            if bot_id in exclude_set:
                continue
            return None, bot_id
        return self.bot_id

    def _workflow_team_catalog(self):
        strengths = {
            'qwen235b': '中文解释、方案讲解、文案整理、对小白友好',
            'gptoss': '快问快答、信息提取、轻量补充',
            'deepseek_v3': '中文深度推理、复杂逻辑、量化与风控',
            'claude_haiku': '快速改写、轻文案、补充说明',
            'claude_sonnet': '复杂任务总控、代码与架构、深度分析',
            'claude_opus': '高难任务、终审、复杂代码与大上下文',
            'chatgpt54': '综合总监、复杂任务编排、强全局把控',
            'gpt5_4': '综合总监、复杂任务编排、强全局把控',
            'gpt5_3_codex': '复杂代码执行、工程修复、编码落地',
            'codex': '复杂代码执行、工程修复、编码落地' }
        catalog = []
        for bot_id in collab_orchestrator._api_callers.keys():
            target_bot = bot_registry.get(bot_id)
            if not target_bot:
                continue
            catalog.append({
                'bot_id': bot_id,
                'name': getattr(target_bot, 'name', bot_id),
                'strength': strengths.get(bot_id, '通用协作与补充执行') })
        return catalog

    
    def _extract_json_object(self, text = None):
        if not text:
            return None
        from json_repair import loads as jloads
        patterns = [
            '```json\\s*(\\{.*?\\})\\s*```',
            '```\\s*(\\{.*?\\})\\s*```']
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            try:
                payload = jloads(match.group(1))
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
        # 回退：直接找 JSON 对象
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                payload = jloads(text[start:end + 1])
                if isinstance(payload, dict):
                    return payload
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        return None

    
    def _fallback_service_options(self, text = None):
        task_text = (text or '').strip()
        return {
            'customer_summary': task_text[:120],
            'missing_info': [
                '如果你暂时说不清细节，也可以先按默认假设推进。'],
            'options': [
                {
                    'id': 1,
                    'title': '极速落地版',
                    'fit': '适合想先快速看到结果的小白',
                    'benefits': '先按合理默认假设推进，最快给出第一版结果',
                    'tradeoffs': '细节不全时，后面可能需要再补一轮修正',
                    'default_assumption': '未补充信息时按当前上下文和常见默认值推进',
                    'recommended': True },
                {
                    'id': 2,
                    'title': '稳妥确认版',
                    'fit': '适合担心返工、想把关键条件说清的人',
                    'benefits': '先把关键问题问清楚，再给较稳的执行方案',
                    'tradeoffs': '前置确认会多一步，整体速度稍慢',
                    'default_assumption': '优先补齐关键条件，再开始执行',
                    'recommended': False },
                {
                    'id': 3,
                    'title': '专家深挖版',
                    'fit': '适合高风险、高复杂度或需要长期迭代的任务',
                    'benefits': '先做评审、风险拆解和分工，再给更完整的结论',
                    'tradeoffs': '耗时最长，但信息最完整、后续扩展更顺',
                    'default_assumption': '优先完整性与风险控制，不追求最快交付',
                    'recommended': False }] }

    
    def _build_service_intake_prompt(self, text = None, feedback_context = None):
        if not feedback_context:
            feedback_context
        return f'''你现在是一个多模型团队里的专业客服接待官，面对的是中文小白用户。\n\n你的任务不是直接开工，而是先把需求接稳、讲明白，再给用户 3 个可选方案。\n\n输出要求：\n1. 用中文，口语化、好懂，不要堆术语。\n2. 先用 1-2 句话复述用户要做什么。\n3. 如果缺信息，只指出最关键的 1-3 条；如果不阻塞，就写“可先按默认假设推进”。\n4. 必须给出 3 个编号方案，每个方案包含：title、fit、benefits、tradeoffs、default_assumption。\n5. 选出一个 recommended=true 的推荐方案。\n6. 最后明确提醒用户只需要回复 1 / 2 / 3 即可继续。\n\n请务必在结尾附上 JSON 代码块，格式如下：\n```json\n{{\n  "customer_summary": "",\n  "missing_info": [""],\n  "options": [\n    {{"id": 1, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": true}},\n    {{"id": 2, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": false}},\n    {{"id": 3, "title": "", "fit": "", "benefits": "", "tradeoffs": "", "default_assumption": "", "recommended": false}}\n  ]\n}}\n```\n\n历史评分反馈：{'暂无历史评分，按标准客服流程接待。'}\n\n用户原话：{text}'''

    
    def _render_service_intake(self, session = None):
        options = session.options if session and session.options else []
        sections = []
        intake_summary = session.intake_summary if session and session.intake_summary else ''
        sections.append(('【需求确认】', [
            intake_summary or (session.original_text if session else '')]))
        if session and session.missing_info:
            sections.append(('【必要信息】', session.missing_info[:3]))
        recommended = 1
        for item in options[:3]:
            option_id = int(item.get('id', 0))
            if item.get('recommended'):
                recommended = option_id
            sections.append((f"【方案 {option_id}】", [
                f"标题：{item.get('title', '')}",
                f"适合谁：{item.get('fit', '')}",
                f"优点：{item.get('benefits', '')}",
                f"代价/风险：{item.get('tradeoffs', '')}",
                f"默认假设：{item.get('default_assumption', '')}"]))
        return format_digest(title = 'OpenClaw「链式讨论」专业客服接单', intro = '先把需求接稳，再给你 3 个方案。你只需要选编号，我就继续往下推进。', sections = sections, footer = f'''推荐优先选方案 {recommended}。请直接回复 1 / 2 / 3。''')

    
    def _parse_workflow_choice(self, text = None, option_count = None):
        if not text:
            return (0, '')
        match = re.search('(?:选|方案)?\\s*([1-9])\\b', text)
        if not match:
            return (0, '')
        choice = int(match.group(1))
        if choice < 1 or choice > max(1, option_count or 3):
            return (0, '')
        note = re.sub('(?:选|方案)?\\s*[1-9]\\b', '', text, count = 1).strip(' ：:，,；;')
        return (choice, note)

    
    def _build_expert_review_prompt(self, session = None, selected_option = None, feedback_context = ('selected_option', dict, 'feedback_context', str, 'return', str)):
        if not feedback_context:
            feedback_context
        if not session.selection_note:
            session.selection_note
        return f'''你现在是相关领域的专家评审官，面对的是一个中文小白用户。\n\n请基于用户原始需求和已选方案，完成：\n1. 判断该方案是否适合当前需求。\n2. 补充必要假设、交付物、风险和小白注意事项。\n3. 将后续执行拆成 2-4 个可并行 workstreams，每个 workstream 标明 type（code / logic / copy / research / qa）。\n\n结尾必须附上 JSON：\n```json\n{{\n  "expert_role": "",\n  "assessment": "",\n  "assumptions": [""],\n  "deliverables": [""],\n  "risks": [""],\n  "beginner_notes": [""],\n  "workstreams": [\n    {{"id": "ws1", "title": "", "goal": "", "type": "logic", "done_when": ""}}\n  ]\n}}\n```\n\n历史评分反馈：{'暂无历史评分。'}\n\n用户原话：{session.original_text}\n用户选中的方案：{json.dumps(selected_option, ensure_ascii = False)}\n用户补充说明：{'无'}'''

    
    def _fallback_expert_plan(self, session = None, selected_option = None):
        pass

    
    def _render_expert_review(self, plan = None):
        if not plan.get('assessment', ''):
            plan.get('assessment', '')
        if not plan.get('assumptions'):
            plan.get('assumptions')

    
    def _pick_lane_bot(self, lane = None, exclude = None):
        exclude_set = set(exclude or [])
        lane_map = {
            'code': [
                'gpt5_3_codex',
                'codex',
                'claude_opus',
                'claude_sonnet',
                'deepseek_v3',
                'gptoss'],
            'logic': [
                'deepseek_v3',
                'claude_sonnet',
                'qwen235b',
                'gpt5_4',
                'chatgpt54'],
            'copy': [
                'qwen235b',
                'claude_haiku',
                'deepseek_v3',
                'gptoss'],
            'research': [
                'qwen235b',
                'deepseek_v3',
                'claude_sonnet',
                'claude_haiku'],
            'qa': [
                'claude_sonnet',
                'qwen235b',
                'deepseek_v3',
                'claude_opus',
                'gptoss'] }
        return self._pick_workflow_bot(lane_map.get(lane, lane_map['logic']), exclude = exclude_set)

    
    def _build_director_prompt(self, session = None, team_catalog = None, feedback_context = ('feedback_context', str, 'return', str)):
        if not feedback_context:
            feedback_context
        return f'''你现在是多模型团队的总监，需要根据专家复核后的方案，把任务按模型特长分配给现有团队并行执行。\n\n要求：\n1. 必须从可用 bot_id 中选择 2-4 个 assignment。\n2. 尽量并行，不要把所有任务都压给同一个模型。\n3. 代码优先交给 code 强的模型，中文解释优先交给 Qwen/中文强模型，复杂逻辑优先交给 DeepSeek/强推理模型。\n4. 再选 1-2 个 validators 做交叉验证。\n\n可用模型：{json.dumps(team_catalog, ensure_ascii = False)}\n专家方案：{json.dumps(session.expert_plan, ensure_ascii = False)}\n历史评分反馈：{'暂无历史评分。'}\n\n请只在结尾附上 JSON：\n```json\n{{\n  "director_summary": "",\n  "assignments": [\n    {{"bot_id": "", "task_id": "ws1", "subtask": "", "reason": ""}}\n  ],\n  "validators": [\n    {{"bot_id": "", "focus": ""}}\n  ]\n}}\n```'''

    
    def _fallback_team_plan(self, session, team_catalog):
        pass

    
    def _render_team_plan(self, team_plan = None, team_catalog = None):
        pass

    
    def _merge_assignments_by_bot(self, assignments):
        grouped = { }
        for item in (assignments or []):
            bot_id = str(item.get('bot_id', '')).strip()
            if not bot_id:
                continue
            bucket = grouped.setdefault(bot_id, {
                'bot_id': bot_id,
                'tasks': [],
                'reasons': [] })
            task_text = str(item.get('subtask', '')).strip()
            if task_text:
                bucket['tasks'].append(task_text)
            reason_text = str(item.get('reason', '')).strip()
            if not reason_text:
                continue
            bucket['reasons'].append(reason_text)
        return list(grouped.values())

    
    def _workflow_timeout(self, bot_id = None):
        if bot_id in frozenset({'codex', 'gpt5_4', 'chatgpt54', 'claude_opus', 'deepseek_v3', 'gpt5_3_codex', 'claude_sonnet'}):
            return 180
        return 120

    
    def _build_worker_prompt(self, session = None, grouped_assignment = None):
        pass

    
    def _build_validation_prompt(self, session = None, focus = None, combined_text = ('focus', str, 'combined_text', str, 'return', str)):
        if not focus:
            focus
        return f'''你现在负责交叉验证。请检查下面这轮团队并行结果，重点关注：{'遗漏、冲突、风险和对小白是否友好'}。\n\n用户原话：{session.original_text}\n已选方案：{session.selected_option_id}\n专家复核：{json.dumps(session.expert_plan, ensure_ascii = False)}\n团队执行结果：\n{combined_text[:5000]}\n\n请在结尾附上 JSON：\n```json\n{{\n  "verdict": "pass",\n  "highlights": [""],\n  "missing": [""],\n  "beginner_notes": [""],\n  "next_iterations": [""]\n}}\n```'''

    
    def _build_summary_prompt(self, session = None, combined_text = None, validation_text = ('combined_text', str, 'validation_text', str, 'return', str)):
        pass

    
    def _fallback_summary_payload(self, session = None):
        status_items = []
        for item in session.execution_results:
            status_items.append(f'''{item.get('bot_name', item.get('bot_id', 'AI'))} 已完成：{item.get('task_summary', '已提交结果')}''')
        if not session.expert_plan.get('beginner_notes'):
            session.expert_plan.get('beginner_notes')

    
    def _render_final_workflow_report(self, session = None, summary_payload = None):
        pass

    
    def _parse_workflow_ratings(self, text = None):
        if not text:
            text

    
    def _workflow_improvement_focus(self, ratings):
        labels = [
            '客服接待',
            '方案评审',
            '任务交付']
        if not ratings:
            return '持续优化整体链路。'
        min_value = min(ratings)

    
    async def _continue_service_workflow(self, update = None, context = None, session = None, text = ('text', str)):
        pass

    
    async def handle_message(self, update, context):
        """处理文本消息 — 流式输出到 Telegram
        
        搬运自 n3d1117/chatgpt-telegram-bot (3.5k⭐) 的流式模式:
        - 发送占位消息 → 流式编辑 → 最终消息
        - 自适应编辑频率（群聊更保守，私聊更激进）
        - Markdown 降级（流式中 Markdown 可能断裂）
        - RetryAfter 退避
        """
        from telegram import constants
        from telegram.error import BadRequest, RetryAfter, TimedOut
        from src.smart_memory import get_smart_memory
        from src.feedback import build_feedback_keyboard, parse_feedback_data, get_feedback_store

        TG_MSG_LIMIT = 4096
        ANTI_FLOOD_DELAY = 0.01

        chat_id = update.effective_chat.id
        user = update.effective_user
        text = (update.message.text or "").strip()
        if not text:
            return

        chat_type = update.effective_chat.type
        is_group = chat_type in ("group", "supergroup")

        if not self._is_authorized(user.id):
            return

        # 中文自然语言命令匹配 — 在 LLM 调用前拦截
        chinese_action = _match_chinese_command(text)
        if chinese_action:
            action_type, action_arg = chinese_action
            await self._dispatch_chinese_action(update, context, action_type, action_arg)
            return  # Chinese command handled, skip LLM call

        # ── Brain 路由（opt-in）──────────────────────────────
        # 中文命令未匹配时，尝试用 OMEGA brain.py 处理可执行请求。
        # 仅在 ENABLE_BRAIN_ROUTING=1 时启用，避免影响现有行为。
        # 使用 _try_fast_parse()（纯正则，无 LLM 调用）做快速判断，
        # 只有可执行意图才路由到 brain；闲聊仍走下方 LLM 流式路径。
        import os
        if os.environ.get("ENABLE_BRAIN_ROUTING", "").lower() in ("1", "true", "yes"):
            try:
                from src.core.intent_parser import IntentParser
                quick_intent = IntentParser()._try_fast_parse(text)
                if quick_intent and quick_intent.is_actionable:
                    from src.core.brain import get_brain
                    brain = get_brain()
                    result = await brain.process_message(
                        source="telegram",
                        message=text,
                        context={"user_id": user.id, "chat_id": chat_id},
                    )
                    if result.success and result.final_result:
                        user_msg = result.to_user_message()
                        if user_msg and user_msg != "✅ 操作已完成":
                            try:
                                safe = md_to_html(user_msg)
                                await update.message.reply_text(safe, parse_mode="HTML")
                            except Exception:
                                await update.message.reply_text(user_msg)
                            return
            except Exception as e:
                logger.debug(f"Brain routing failed, falling through to LLM: {e}")

        # 消息频率限制 — 防止用户刷屏导致 API 过载
        from src.bot.globals import rate_limiter
        if rate_limiter:
            allowed, reason = rate_limiter.check(self.bot_id, "private" if not is_group else "group")
            if not allowed:
                logger.info("[%s] 消息频率限制: %s (user=%s)", self.name, reason, user.id)
                return

        # 群聊：检查是否应该回复
        if is_group:
            should, reason = await self._should_respond_async(
                text, chat_type, update.message.message_id, user.id
            )
            if not should:
                return

        # 优先级分类 — 关键消息（止损/风控/紧急）优先处理
        from src.bot.globals import priority_message_queue
        _msg_priority = None
        if priority_message_queue:
            try:
                _msg_priority = priority_message_queue.classify_priority(
                    text=text,
                    chat_id=chat_id,
                    user_id=user.id,
                    is_private=not is_group,
                    is_mentioned=not is_group,  # 私聊视为 mentioned
                )
                # 入队追踪（不阻塞处理，仅用于统计和优先级感知）
                from src.chat_router import PrioritizedMessage
                import time as _ptime
                await priority_message_queue.enqueue(PrioritizedMessage(
                    priority=_msg_priority.value,
                    timestamp=_ptime.time(),
                    chat_id=chat_id,
                    user_id=user.id,
                    text=text[:200],
                    bot_id=getattr(self, 'bot_id', ''),
                ))
            except Exception:
                logger.debug("Silenced exception", exc_info=True)  # 优先级队列不影响主流程

        # 智能记忆管道 — 记录用户消息（异步，不阻塞）
        _sm = get_smart_memory()
        if _sm:
            _t = asyncio.create_task(_sm.on_message(chat_id, user.id, "user", text, self.bot_id))
            _t.add_done_callback(lambda t: t.exception() and logger.debug("智能记忆(用户消息)后台任务异常: %s", t.exception()))

        # 发送 typing 指示器
        typing_task = asyncio.create_task(self._keep_typing(chat_id, context))

        try:
            sent_message = None
            prev_text = ""
            backoff = 0
            chunk_idx = 0
            final_content = ""
            model_used = getattr(self, 'model', 'unknown') or 'unknown'

            # Phase 1: "思考中" 占位符（搬运自 karfly/chatgpt_telegram_bot）
            sent_message = await update.message.reply_text(
                "🤔 思考中...",
                reply_to_message_id=update.message.message_id if is_group else None,
            )

            async for content, status in self._call_api_stream(
                chat_id, text, save_history=True, chat_type=chat_type
            ):
                if not content:
                    continue
                final_content = content

                # Telegram 消息长度限制 — 超长时分割发送
                if len(content) > TG_MSG_LIMIT:
                    if sent_message and prev_text:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent_message.message_id,
                                text=prev_text[:TG_MSG_LIMIT],
                            )
                        except BadRequest:
                            pass
                    # 发送所有溢出部分（不截断）
                    remaining = content[TG_MSG_LIMIT:]
                    while remaining:
                        chunk = remaining[:TG_MSG_LIMIT]
                        remaining = remaining[TG_MSG_LIMIT:]
                        try:
                            sent_message = await update.message.reply_text(chunk)
                            prev_text = chunk
                        except Exception as e:
                            logger.warning(f"[{self.bot_id}] 发送溢出消息失败: {e}")
                            break
                    continue

                cutoff = self._stream_cutoff(is_group, content) + backoff

                if chunk_idx == 0:
                    # Phase 2: 首个 token — 替换"思考中"为实际内容
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=content + " ▌",
                        )
                        prev_text = content
                        chunk_idx += 1
                    except Exception as e:
                        logger.warning(f"[{self.bot_id}] 替换占位符失败: {e}")
                        break

                elif abs(len(content) - len(prev_text)) > cutoff or status == "finished":
                    if not sent_message:
                        break

                    if status != "finished":
                        display = (content + " ▌")[:TG_MSG_LIMIT]

                    try:
                        # Phase 3: 完成时用 md_to_html 安全渲染 + HTML parse_mode
                        if status == "finished":
                            try:
                                display = md_to_html(content) + f"\n\n<code>via {getattr(self, 'name', self.bot_id)} · {model_used.split('/')[-1]}</code>"
                                display = display[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.HTML
                            except Exception:
                                model_short = model_used.split("/")[-1]
                                display = (content + f"\n\n`via {getattr(self, 'name', self.bot_id)} · {model_short}`")[:TG_MSG_LIMIT]
                                parse_mode = constants.ParseMode.MARKDOWN
                        else:
                            parse_mode = None
                        reply_markup = build_feedback_keyboard(self.bot_id, model_used, chat_id) if status == "finished" else None
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=display,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup,
                        )
                        prev_text = content
                    except BadRequest as e:
                        err_msg = str(e)
                        if "Message is not modified" in err_msg:
                            pass
                        elif "parse" in err_msg.lower() or "can't" in err_msg.lower():
                            try:
                                await context.bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=sent_message.message_id,
                                    text=display,
                                    reply_markup=reply_markup,
                                )
                                prev_text = content
                            except BadRequest:
                                pass
                        else:
                            backoff += 5
                            logger.debug(f"[{self.bot_id}] edit_message BadRequest: {err_msg}")
                    except RetryAfter as e:
                        backoff += 5
                        await asyncio.sleep(e.retry_after)
                    except TimedOut:
                        backoff += 5
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        backoff += 5
                        logger.debug(f"[{self.bot_id}] edit_message 异常: {e}")

                    await asyncio.sleep(ANTI_FLOOD_DELAY)
                    chunk_idx += 1

            # 流式没有产出任何内容 → 降级到非流式
            if chunk_idx == 0:
                reply = await self._call_api(chat_id, text, save_history=True, chat_type=chat_type)
                if reply:
                    final_content = reply
                    fb_markup = build_feedback_keyboard(self.bot_id, model_used, chat_id)
                    try:
                        safe_reply = md_to_html(reply)
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=safe_reply[:TG_MSG_LIMIT],
                            parse_mode=constants.ParseMode.HTML,
                            reply_markup=fb_markup,
                        )
                    except BadRequest:
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=sent_message.message_id,
                                text=reply[:TG_MSG_LIMIT],
                                reply_markup=fb_markup,
                            )
                        except Exception:
                            logger.debug("Silenced exception", exc_info=True)
                else:
                    # 空回复 — 更新占位符
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text="暂时无法回复，请稍后再试",
                        )
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)
                    logger.info(f"[{self.bot_id}] 空回复 (chat={chat_id})")

            # 记录 AI 回复到智能记忆
            if _sm and final_content:
                _t2 = asyncio.create_task(_sm.on_message(chat_id, user.id, "assistant", final_content[:500], self.bot_id))
                _t2.add_done_callback(lambda t: t.exception() and logger.debug("智能记忆(AI回复)后台任务异常: %s", t.exception()))

            # 可选语音回复 — 用户通过 /voice 开启后，短回复自动附带语音
            try:
                if final_content and context.user_data.get("voice_reply") and len(final_content) < 500:
                    from src.tts_engine import text_to_voice
                    audio_bytes = await text_to_voice(final_content)
                    if audio_bytes:
                        await update.message.reply_voice(io.BytesIO(audio_bytes))
            except Exception:
                logger.debug("Silenced exception", exc_info=True)  # 语音是可选功能，不阻塞主流程

        except Exception as e:
            logger.error(f"[{self.bot_id}] handle_message 异常: {e}", exc_info=True)

            # 清理流式光标 ▌ — 防止异常时光标永久残留
            if sent_message and prev_text:
                try:
                    clean_text = prev_text.rstrip(" ▌")
                    if clean_text:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=clean_text + "\n\n⚠️ 回复中断",
                        )
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)

            # 分类错误提示 — 比"出错了"更有信息量
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                user_msg = "回复超时了，模型可能比较忙，请稍后再试"
            elif "rate" in err_str or "429" in err_str or "quota" in err_str:
                user_msg = "请求太频繁了，请等几秒再发"
            elif "connect" in err_str or "network" in err_str or "ssl" in err_str:
                user_msg = "网络连接出了问题，正在自动切换线路"
            elif "auth" in err_str or "401" in err_str or "403" in err_str:
                user_msg = "API 认证失败，管理员已收到通知"
            else:
                user_msg = "处理消息时遇到问题，请稍后重试"
            try:
                from src.telegram_ux import send_error_with_retry
                await send_error_with_retry(update, context, e, retry_command="")
            except Exception:
                try:
                    await update.message.reply_text(user_msg)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def handle_voice(self, update, context):
        """处理语音消息 — 搬运自 father-bot/chatgpt-telegram-bot 的 Whisper 模式
        
        下载语音 → OpenAI Whisper 转文字 → 当作文本消息处理
        """
        if not self._is_authorized(update.effective_user.id):
            return

        chat_id = update.effective_chat.id
        voice = update.message.voice or update.message.audio
        if not voice:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            # 下载语音文件
            file = await context.bot.get_file(voice.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            buf.seek(0)
            buf.name = "voice.ogg"

            # 尝试 OpenAI Whisper API
            transcribed = None
            try:
                import os
                openai_key = os.environ.get("OPENAI_API_KEY", "")
                if openai_key:
                    import httpx
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.post(
                            "https://api.openai.com/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {openai_key}"},
                            files={"file": ("voice.ogg", buf, "audio/ogg")},
                            data={"model": "whisper-1"},
                        )
                        if resp.status_code == 200:
                            transcribed = resp.json().get("text", "")
            except Exception as whisper_err:
                logger.debug("[Voice] Whisper API 失败: %s", whisper_err)

            if not transcribed:
                await update.message.reply_text(
                    "🎤 语音识别暂不可用（需要 OPENAI_API_KEY）\n请发送文字消息",
                    reply_to_message_id=update.message.message_id,
                )
                return

            # 显示识别结果，然后当作文本处理
            await update.message.reply_text(
                f"🎤 识别: {transcribed[:200]}",
                reply_to_message_id=update.message.message_id,
            )

            # 伪造文本消息，复用 handle_message 流程
            update.message.text = transcribed
            await self.handle_message(update, context)

        except Exception as e:
            logger.error("[Voice] 语音处理失败: %s", e)
            await update.message.reply_text("🎤 语音处理失败，请发送文字消息")

    @staticmethod
    def _stream_cutoff(is_group: bool, content: str) -> int:
        """自适应编辑频率 — 搬运自 n3d1117/chatgpt-telegram-bot
        
        群聊更保守（Telegram 对群聊有更严格的 flood 限制），
        私聊更激进（用户体验优先）。
        """
        n = len(content)
        if is_group:
            if n > 1000: return 180
            if n > 200: return 120
            if n > 50: return 90
            return 50
        else:
            if n > 1000: return 90
            if n > 200: return 45
            if n > 50: return 25
            return 15

    async def _keep_typing(self, chat_id: int, context):
        """持续发送 typing 指示器 — 搬运自 n3d1117 的 wrap_with_indicator"""
        from telegram.constants import ChatAction
        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4.5)
        except asyncio.CancelledError:
            raise  # 让 finally 正常处理
        except Exception as e:
            # 网络错误等 — 静默退出但记录，不影响主流程
            logger.debug(f"[typing] chat={chat_id} 停止: {e}")

    
    async def _run_chain_discuss(self, update = None, context = None, text = ('text', str)):
        '''启动新版链式讨论工作流。'''
        pass

    
    async def handle_photo(self, update, context):
        '''处理图片消息 — OCR → 场景路由 → 业务决策链'''
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            caption = update.message.caption or ""
            is_group = update.effective_chat.type in ("group", "supergroup")
            
            # 群聊门控：仅在被 @ 或 caption 含触发词时才 OCR
            if is_group:
                bot_username = (await context.bot.get_me()).username or ""
                mentioned = f"@{bot_username}" in (caption or "")
                trigger = any(w in caption for w in ("OCR", "ocr", "识别", "文字", "提取", "分析", "竞品", "财报"))
                if not mentioned and not trigger:
                    return
            
            # 发送处理中提示
            hint_msg = await update.message.reply_text("🔍 正在识别图片文字...")
            
            # 下载图片
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            image_bytes = buf.getvalue()
            
            logger.info(f"[OCR] 收到图片 from {user.id}, {len(image_bytes)} bytes")
            
            # 调用 OCR
            result: OcrResult = await ocr_image(
                image_bytes,
                mime_type="image/jpeg",
                user_id=user.id,
                file_unique_id=photo.file_unique_id,
            )
            
            # 删除处理中提示
            try:
                await hint_msg.delete()
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
            
            # OCR 失败
            if not result.ok:
                await send_long_message(chat_id, f"⚠️ OCR 失败: {result.error}", context,
                                        reply_to_message_id=update.message.message_id)
                return
            
            # OCR 无文字 → 降级到 Vision 模型分析
            if not result.text:
                try:
                    from src.tools.vision import analyze_image
                    vision_prompt = caption or "描述这张图片的内容"
                    vision_result = await analyze_image(bytes(image_bytes), vision_prompt)
                    if vision_result:
                        await send_long_message(
                            chat_id,
                            f"🖼️ 图片分析:\n\n{vision_result}",
                            context,
                            reply_to_message_id=update.message.message_id,
                        )
                        return
                except Exception as ve:
                    logger.debug(f"[OCR] Vision fallback 失败: {ve}")

                await send_long_message(chat_id, "📷 图片已收到，未识别到文字内容。", context,
                                        reply_to_message_id=update.message.message_id)
                return
            
            # 场景路由
            scene_match = classify_ocr_scene(result.text, caption)
            
            if scene_match.scene == OcrScene.FINANCIAL:
                # 交易/财报场景
                proc_result = await process_financial_scene(
                    result.text, caption, user.id, chat_id, shared_memory)
                
                tag = " (缓存)" if result.cached else ""
                reply_parts = [f"📄 OCR 识别结果{tag}:\n\n{result.text}"]
                reply_parts.append(f"\n{'─' * 20}")
                reply_parts.append(f"🎯 场景: 交易分析 ({scene_match.confidence:.0%})")
                if proc_result.success:
                    reply_parts.append(proc_result.summary)
                    if proc_result.next_step:
                        reply_parts.append(f"\n💡 {proc_result.next_step}")
                
                await send_long_message(chat_id, "\n".join(reply_parts), context,
                                        reply_to_message_id=update.message.message_id)
                
                # 注入对话上下文（可追问）
                if proc_result.context_injection:
                    try:
                        history_store.add_message(
                            getattr(self, 'bot_id', 'system'), chat_id,
                            "assistant", proc_result.context_injection)
                    except Exception as e:
                        logger.warning(f"[OCR] 交易场景上下文注入失败: {e}")
                if proc_result.auto_invest_topic and not is_group:
                    try:
                        await send_long_message(chat_id,
                            f"🚀 自动触发投资分析: {proc_result.auto_invest_topic}\n"
                            "发送 /stop_discuss 可中断", context)
                        # 模拟 /invest 命令
                        context.args = proc_result.auto_invest_topic.split()
                        await self.cmd_invest(update, context)
                    except Exception as e:
                        logger.error(f"[OCR] 自动触发 /invest 失败: {e}")
            
            elif scene_match.scene == OcrScene.ECOMMERCE:
                # 电商/竞品场景
                proc_result = await process_ecommerce_scene(
                    result.text, caption, user.id, chat_id, shared_memory)
                
                tag = " (缓存)" if result.cached else ""
                reply_parts = [f"📄 OCR 识别结果{tag}:\n\n{result.text}"]
                reply_parts.append(f"\n{'─' * 20}")
                reply_parts.append(f"🎯 场景: 竞品分析 ({scene_match.confidence:.0%})")
                if proc_result.success:
                    reply_parts.append(proc_result.summary)
                    if proc_result.next_step:
                        reply_parts.append(f"\n💡 定价建议: {proc_result.next_step}")
                
                await send_long_message(chat_id, "\n".join(reply_parts), context,
                                        reply_to_message_id=update.message.message_id)
                
                # 注入对话上下文（可追问）
                if proc_result.context_injection:
                    try:
                        history_store.add_message(
                            getattr(self, 'bot_id', 'system'), chat_id,
                            "assistant", proc_result.context_injection)
                    except Exception as e:
                        logger.warning(f"[OCR] 电商场景上下文注入失败: {e}")
            
            else:
                # 通用场景: OCR 文字 + Vision 补充分析
                tag = " (缓存)" if result.cached else ""
                reply = f"📄 OCR 识别结果{tag}:\n\n{result.text}"
                if caption:
                    reply += f"\n\n💬 附言: {caption}"

                # Vision 补充: 用户有 caption 指令时，用 Vision 模型做进一步分析
                if caption and any(w in caption for w in ("分析", "解释", "翻译", "总结", "看看", "什么意思")):
                    try:
                        from src.tools.vision import analyze_image
                        vision_result = await analyze_image(
                            bytes(image_bytes),
                            f"图片中的文字内容如下:\n{result.text[:500]}\n\n用户要求: {caption}",
                        )
                        if vision_result:
                            reply += f"\n\n{'─' * 20}\n🖼️ 图片分析:\n{vision_result}"
                    except Exception as ve:
                        logger.debug(f"[OCR] Vision 补充分析失败: {ve}")

                await send_long_message(chat_id, reply, context,
                                        reply_to_message_id=update.message.message_id)
                
        except Exception as e:
            logger.error(f"[OCR] handle_photo 异常: {e}", exc_info=True)
            try:
                await send_long_message(
                    update.effective_chat.id, f"⚠️ 图片处理异常: {e}", context,
                    reply_to_message_id=update.message.message_id)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

    
    async def handle_trade_callback(self, update, context):
        '''处理投资分析会议后的一键下单按钮回调
        callback_data 格式:
          itrade:{trade_key}:{idx}     — 执行单笔交易
          itrade_all:{trade_key}       — 执行全部交易
          itrade_cancel:{trade_key}    — 取消全部
        '''
        from src.bot.globals import _pending_trades, ibkr
        from telegram import InlineKeyboardMarkup

        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("itrade_cancel:"):
            trade_key = data.split(":")[1]
            _pending_trades.pop(trade_key, None)
            await query.edit_message_text("❌ 已取消全部交易。")
            return

        if data.startswith("itrade_all:"):
            trade_key = data.split(":")[1]
            pending = _pending_trades.pop(trade_key, None)
            if not pending:
                await query.edit_message_text("⚠️ 交易已过期，请重新执行 /invest")
                return
            trades = pending.get("trades", [])
            results = []
            for t in trades:
                try:
                    ret = await ibkr.place_order(
                        symbol=t["symbol"], action=t["action"],
                        quantity=t["qty"],
                        stop_loss=t.get("stop_loss"),
                        take_profit=t.get("take_profit"),
                    )
                    emoji = "✅" if ret.get("success") else "❌"
                    results.append(f"{emoji} {t['action']} {t['symbol']} x{t['qty']}: {ret.get('message', 'OK')}")
                except Exception as e:
                    results.append(f"❌ {t['symbol']}: {e}")
            await query.edit_message_text("📋 执行结果:\n\n" + "\n".join(results))
            return

        if data.startswith("itrade:"):
            parts = data.split(":")
            if len(parts) < 3:
                return
            trade_key = parts[1]
            idx = int(parts[2])
            pending = _pending_trades.get(trade_key)
            if not pending:
                await query.edit_message_text("⚠️ 交易已过期，请重新执行 /invest")
                return
            trades = pending.get("trades", [])
            if idx >= len(trades):
                return
            t = trades[idx]
            try:
                ret = await ibkr.place_order(
                    symbol=t["symbol"], action=t["action"],
                    quantity=t["qty"],
                    stop_loss=t.get("stop_loss"),
                    take_profit=t.get("take_profit"),
                )
                emoji = "✅" if ret.get("success") else "❌"
                await query.message.reply_text(
                    f"{emoji} {t['action']} {t['symbol']} x{t['qty']}: {ret.get('message', 'OK')}")
            except Exception as e:
                await query.message.reply_text(f"❌ {t['symbol']} 执行失败: {e}")

    async def handle_document_ocr(self, update, context):
        '''处理文档消息（PDF/DOCX/PPTX/XLSX/图片）— Docling 结构化理解 + OCR 降级'''
        try:
            chat_id = update.effective_chat.id
            user = update.effective_user
            doc = update.message.document
            mime = doc.mime_type or ""
            fname = doc.file_name or "document"
            caption = update.message.caption or ""
            is_group = update.effective_chat.type in ("group", "supergroup")
            
            # 仅处理图片、PDF 和 Office 文档
            supported_mimes = (
                "image/", "application/pdf",
                "application/vnd.openxmlformats-officedocument",  # docx/pptx/xlsx
                "application/msword",  # .doc
                "application/vnd.ms-excel",  # .xls
                "application/vnd.ms-powerpoint",  # .ppt
            )
            if not any(mime.startswith(m) for m in supported_mimes):
                return
            
            # 群聊门控
            if is_group:
                bot_username = (await context.bot.get_me()).username or ""
                mentioned = f"@{bot_username}" in (caption or "")
                trigger = any(w in caption for w in ("OCR", "ocr", "识别", "文字", "提取", "分析", "总结", "摘要"))
                if not mentioned and not trigger:
                    return
            
            # 处理中提示
            hint_msg = await update.message.reply_text(f"🔍 正在分析 {fname}...")
            
            logger.info(f"[DOC] 收到文档 {fname} ({mime}, {doc.file_size} bytes) from {user.id}")
            
            file = await context.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            file_bytes = buf.getvalue()

            # ── Docling 结构化理解 (优先) ──────────────────────────
            docling_supported = ('.pdf', '.docx', '.pptx', '.xlsx', '.doc')
            docling_handled = False

            if fname.lower().endswith(docling_supported):
                try:
                    from src.tools.docling_service import (
                        convert_document, summarize_document, HAS_DOCLING,
                    )
                    if HAS_DOCLING:
                        # 写入临时文件 — Docling 需要文件路径
                        import os, tempfile
                        suffix = os.path.splitext(fname)[1] or ".pdf"
                        with tempfile.NamedTemporaryFile(
                            suffix=suffix, delete=False,
                        ) as tmp:
                            tmp.write(file_bytes)
                            local_path = tmp.name

                        try:
                            if caption:
                                # 用户附带了问题 → 摘要+问答模式
                                result_text = await summarize_document(
                                    local_path, question=caption,
                                )
                            else:
                                # 无问题 → 自动摘要
                                result_text = await summarize_document(local_path)

                            if result_text:
                                # 删除处理中提示
                                try:
                                    await hint_msg.delete()
                                except Exception:
                                    logger.debug("Silenced exception", exc_info=True)
                                try:
                                    safe = md_to_html(result_text)
                                    await update.message.reply_text(
                                        safe, parse_mode="HTML",
                                        reply_to_message_id=update.message.message_id,
                                    )
                                except Exception:
                                    # HTML 渲染失败 → 纯文本降级
                                    await send_long_message(
                                        chat_id, result_text, context,
                                        reply_to_message_id=update.message.message_id,
                                    )
                                docling_handled = True
                        finally:
                            # 清理临时文件
                            try:
                                os.unlink(local_path)
                            except Exception:
                                logger.debug("Silenced exception", exc_info=True)
                except Exception as e:
                    logger.debug(f"[DOC] Docling 处理失败，降级到 OCR: {e}")

            if docling_handled:
                return

            # ── OCR 降级 (图片 + Docling 失败时) ──────────────────
            result: OcrResult = await ocr_image(
                file_bytes,
                mime_type=mime,
                user_id=user.id,
                file_unique_id=doc.file_unique_id,
            )
            
            # 删除处理中提示
            try:
                await hint_msg.delete()
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
            
            if result.ok and result.text:
                tag = " (缓存)" if result.cached else ""
                reply = f"📄 {fname} 识别结果{tag}:\n\n{result.text}"
                if caption:
                    reply += f"\n\n💬 附言: {caption}"
                await send_long_message(chat_id, reply, context,
                                        reply_to_message_id=update.message.message_id)
            elif result.ok and not result.text:
                await send_long_message(chat_id, f"📎 {fname} 已收到，未识别到文字内容。", context,
                                        reply_to_message_id=update.message.message_id)
            else:
                await send_long_message(chat_id, f"⚠️ {fname} OCR 失败: {result.error}", context,
                                        reply_to_message_id=update.message.message_id)
        except Exception as e:
            logger.error(f"[DOC] handle_document_ocr 异常: {e}", exc_info=True)
            try:
                await send_long_message(
                    update.effective_chat.id, f"⚠️ 文档处理异常: {e}", context,
                    reply_to_message_id=update.message.message_id)
            except Exception:
                logger.debug("Silenced exception", exc_info=True)



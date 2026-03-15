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
        if not m_bounty_scan.group(1):
            m_bounty_scan.group(1)
        kw = ''.strip()
        return ('ops_bounty_scan', kw)
    if None.fullmatch('(赏金列表|赏金机会|赏金看板)', t):
        return ('ops_bounty_list', '')
    if re.fullmatch('(赏金top|赏金排行|高收益赏金)', t):
        return ('ops_bounty_top', '')
    if re.fullmatch('(开工赚钱|打开赏金机会|开赏金链接)', t):
        return ('ops_bounty_open', '')
    m_tweet_plan = re.search('(?:推文计划|分析推文|推文执行计划)\\s+(.+)', t)
    if m_tweet_plan:
        return ('ops_tweet_plan', m_tweet_plan.group(1).strip())
    m_tweet_run = None.search('(?:执行推文|推文执行|推文赚钱|跟着推文赚钱)\\s+(.+)', t)
    if m_tweet_run:
        return ('ops_tweet_run', m_tweet_run.group(1).strip())
    m_docs_search = None.search('(?:文档检索|文档搜索|搜文档)\\s+(.+)', t)
    if m_docs_search:
        return ('ops_docs_search', m_docs_search.group(1).strip())
    m_docs_index = None.search('(?:建立文档索引|索引文档)\\s*(.*)', t)
    if m_docs_index and re.search('文档', t):
        if not m_docs_index.group(1):
            m_docs_index.group(1)
        if not ''.strip():
            ''.strip()
        target = '.'
        return ('ops_docs_index', target)
    m_meeting = None.search('(?:会议纪要|总结会议)\\s+(.+)', t)
    if m_meeting:
        return ('ops_meeting', m_meeting.group(1).strip())
    m_content = None.search('(?:社媒选题|内容选题|写作选题)\\s*(.*)', t)
    if m_content and re.search('选题', t):
        if not m_content.group(1):
            m_content.group(1)
        if not ''.strip():
            ''.strip()
        keyword = 'AI'
        return ('ops_content', keyword)
    m_social_plan = None.search('(?:社媒计划|发文计划|今日发什么)\\s*(.*)', t)
    if m_social_plan and re.search('计划|发什么', t):
        if not m_social_plan.group(1):
            m_social_plan.group(1)
        return ('social_plan', ''.strip())
    m_social_repost = None.search('(?:双平台改写|改写双平台|改写成双平台|双平台草稿)\\s*(.*)', t)
    if m_social_repost:
        if not m_social_repost.group(1):
            m_social_repost.group(1)
        return ('social_repost', ''.strip())
    if None.fullmatch('(数字生命首发|首发包|社媒首发包|数字生命人设首发)', t):
        return ('social_launch', '')
    if re.fullmatch('(当前社媒人设|社媒人设|数字生命人设|当前人设)', t):
        return ('social_persona', '')
    m_topic = re.search('(?:研究|分析|看看|学习)(.+?)(?:题材|方向|内容)', t)
    if m_topic:
        return ('social_topic', m_topic.group(1).strip())
    m_xhs = None.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到小红书', t)
    if m_xhs:
        return ('social_xhs', m_xhs.group(1).strip())
    m_x = None.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到(?:x|推特|推文)', t, re.IGNORECASE)
    if m_x:
        return ('social_x', m_x.group(1).strip())
    m_dual = None.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?(?:双平台|同时发|发到两个平台)', t)
    if m_dual:
        return ('social_post', m_dual.group(1).strip())
    if None.fullmatch('(一键发文|热点发文|热点一键发文|蹭热点发文|自动发文)', t):
        return ('social_hotpost', '')
    m_hotpost = re.search('(?:一键发文|热点发文|蹭热点发文|自动发文)\\s+(.+)', t)
    if m_hotpost:
        return ('social_hotpost', m_hotpost.group(1).strip())
    m_monitor_add = None.search('(?:添加资讯监控|新增资讯监控|监控关键词)\\s+(.+)', t)
    if m_monitor_add:
        return ('ops_monitor_add', m_monitor_add.group(1).strip())
    if None.fullmatch('(资讯监控列表|新闻监控列表)', t):
        return ('ops_monitor_list', '')
    if re.fullmatch('(运行资讯监控|扫描资讯监控|立即扫描资讯监控)', t):
        return ('ops_monitor_run', '')
    m_remind = re.search('(\\d+)\\s*分钟后提醒我\\s+(.+)', t)
    if m_remind:
        return ('ops_life_remind', f'''{m_remind.group(1)}|||{m_remind.group(2).strip()}''')
    m_remind_default = None.search('提醒我\\s+(.+)', t)
    if m_remind_default:
        return ('ops_life_remind', f'''30|||{m_remind_default.group(1).strip()}''')
    m_project = None.search('(?:项目周报|生成项目周报)\\s*(.*)', t)
    if m_project and re.search('项目周报', t):
        if not m_project.group(1):
            m_project.group(1)
        if not ''.strip():
            ''.strip()
        target = '.'
        return ('ops_project', target)
    m_dev = None.search('(?:开发流程|执行开发流程|跑开发流程)\\s*(.*)', t)
    if m_dev and re.search('开发流程', t):
        if not m_dev.group(1):
            m_dev.group(1)
        if not ''.strip():
            ''.strip()
        target = '.'
        return ('ops_dev', target)
    if None.search('(开始|自动|帮我|一键).{0,2}投资|找.{0,2}机会|自动交易|帮我(赚钱|炒股|交易)|今天买什么|有什么(机会|可以买)', t):
        return ('auto_invest', t)
    if None.search('扫描|扫一下|扫一扫|看看市场|市场扫描|全市场', t):
        return ('scan', '')
    m = re.search('(?:分析|技术分析|看看|研究)\\s*([A-Za-z]{1,5}(?:-USD)?)', t)
    if m:
        return ('ta', m.group(1).upper())
    m = None.search('([A-Za-z]{1,5})\\s*(?:信号|买卖|怎么样|能买吗|能不能买)', t)
    if m:
        return ('signal', m.group(1).upper())
    m = None.search('([A-Za-z]{1,5})\\s*(?:多少钱|股价|价格|行情)', t)
    if m:
        return ('quote', m.group(1).upper())
    m = None.search('(?:查|看).{0,2}(?:行情|价格)\\s*([A-Za-z]{1,5})?', t)
    if m and m.group(1):
        return ('quote', m.group(1).upper())
    if None.search('市场概览|大盘|今天行情|行情怎么样|市场怎么样', t):
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
        if not m_bt.group(1):
            m_bt.group(1)
        sym = ''.strip().upper()
        return ('backtest', sym)
    if None.search('再平衡|调仓|rebalance|配置组合|目标配置', t):
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
        pass

    
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
        patterns = [
            '```json\\s*(\\{.*?\\})\\s*```',
            '```\\s*(\\{.*?\\})\\s*```']
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            payload = json.loads(match.group(1))
            if isinstance(payload, dict):
                
                return patterns, payload
        pass  # auto
        if start >= 0 and end > start:
            payload = json.loads(text[start:end + 1])
            if isinstance(payload, dict):
                return payload
            return None
        return None

    
    def _fallback_service_options(self, text = None):
        if not text:
            text
        task_text = ''.strip()
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
        if not session.options:
            session.options
        options = []
        sections = []
        if not session.intake_summary:
            session.intake_summary
        sections.append(('【需求确认】', [
            session.original_text]))
        if session.missing_info:
            sections.append(('【必要信息】', session.missing_info[:3]))
        for item in options[:3]:
            if not item.get('id', 0):
                item.get('id', 0)
            option_id = int(0)
            sections.append((f'''【方案 {option_id}】''', [
                f'''标题：{item.get('title', '')}''',
                f'''适合谁：{item.get('fit', '')}''',
                f'''优点：{item.get('benefits', '')}''',
                f'''代价/风险：{item.get('tradeoffs', '')}''',
                f'''默认假设：{item.get('default_assumption', '')}''']))
        return format_digest(title = 'OpenClaw「链式讨论」专业客服接单', intro = '先把需求接稳，再给你 3 个方案。你只需要选编号，我就继续往下推进。', sections = sections, footer = f'''推荐优先选方案 {recommended}。请直接回复 1 / 2 / 3。''')

    
    def _parse_workflow_choice(self, text = None, option_count = None):
        if not text:
            text
        match = re.search('(?:选|方案)?\\s*([1-9])\\b', '')
        if not match:
            return (0, '')
        choice = int(match.group(1))
        if choice < 1 or choice > max(1, option_count):
            return (0, '')
        if not text:
            text
        note = re.sub('(?:选|方案)?\\s*[1-9]\\b', '', '', count = 1).strip(' ：:，,；;')
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
        if not exclude:
            exclude
        exclude_set = set([])
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
        if not assignments:
            assignments
        for item in []:
            if not item.get('bot_id', ''):
                item.get('bot_id', '')
            bot_id = str('').strip()
            if not bot_id:
                continue
            bucket = grouped.setdefault(bot_id, {
                'bot_id': bot_id,
                'tasks': [],
                'reasons': [] })
            if not item.get('subtask', ''):
                item.get('subtask', '')
            task_text = str('').strip()
            if task_text:
                bucket['tasks'].append(task_text)
            if not item.get('reason', ''):
                item.get('reason', '')
            reason_text = str('').strip()
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
        pass

    
    async def _run_chain_discuss(self, update = None, context = None, text = ('text', str)):
        '''启动新版链式讨论工作流。'''
        pass

    
    async def handle_photo(self, update, context):
        '''处理图片消息'''
        pass

    
    async def handle_trade_callback(self, update, context):
        '''处理投资分析会议后的一键下单按钮回调'''
        pass



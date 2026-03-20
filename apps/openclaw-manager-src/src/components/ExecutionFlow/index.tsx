import { useState, useCallback, useEffect, useRef } from 'react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, addEdge, BackgroundVariant, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Play, Square, Loader2, Workflow, Terminal } from 'lucide-react';
import { invoke } from '@tauri-apps/api/core';
import { isTauri } from '../../lib/tauri';
import clsx from 'clsx';

const initialNodes: Node[] = [
  { id: 'hub', position: { x: 250, y: 50 }, data: { label: '执行引擎核心 (Hub)' }, type: 'input', className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'llm', position: { x: 100, y: 150 }, data: { label: 'AI 决策集群 (LLM)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'browser', position: { x: 400, y: 150 }, data: { label: '浏览器代理 (Browser-Use)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'mem0', position: { x: 250, y: 250 }, data: { label: '记忆检索器 (Mem0)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'trader', position: { x: 50, y: 250 }, data: { label: '量化交易 (Freqtrade)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
];

const initialEdges = [
  { id: 'e-hub-llm', source: 'hub', target: 'llm', animated: true, style: { stroke: '#f94d3a' } },
  { id: 'e-hub-browser', source: 'hub', target: 'browser', animated: true, style: { stroke: '#22d3ee' } },
  { id: 'e-llm-mem0', source: 'llm', target: 'mem0', animated: true, style: { stroke: '#a78bfa' } },
  { id: 'e-llm-trader', source: 'llm', target: 'trader', animated: true, style: { stroke: '#4ade80' } },
];

export function ExecutionFlow() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [isRunning, setIsRunning] = useState(false);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const [useRealLogs, setUseRealLogs] = useState(true);

  // Auto-scroll logs
  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const addLog = useCallback((msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`].slice(-50));
  }, []);

  const parseLogToNode = (log: string) => {
    const lower = log.toLowerCase();
    if (lower.includes('litellm') || lower.includes('llm') || lower.includes('api_pool')) return 'llm';
    if (lower.includes('mem0') || lower.includes('memory') || lower.includes('rag')) return 'mem0';
    if (lower.includes('browser') || lower.includes('playwright') || lower.includes('xpath')) return 'browser';
    if (lower.includes('freqtrade') || lower.includes('trade') || lower.includes('ibkr')) return 'trader';
    if (lower.includes('hub') || lower.includes('execute') || lower.includes('task')) return 'hub';
    return null;
  };

  useEffect(() => {
    if (!isTauri() || !useRealLogs) return;
    
    // Poll real logs from the clawbot backend
    const pollLogs = async () => {
      try {
        const newLogs = await invoke<string[]>('get_managed_service_logs', { label: 'ai.openclaw.agent', lines: 20 });
        if (newLogs && newLogs.length > 0) {
          setLogs(newLogs);
          // Highlight node based on the latest log
          const latestLog = newLogs[newLogs.length - 1];
          const parsedNode = parseLogToNode(latestLog);
          if (parsedNode) setActiveNode(parsedNode);
          
          setIsRunning(true);
        }
      } catch (e) {
        // Fallback to simulation if backend logs are unavailable
      }
    };
    
    pollLogs();
    const interval = setInterval(pollLogs, 2000);
    return () => clearInterval(interval);
  }, [useRealLogs]);

  const simulateExecution = () => {
    setUseRealLogs(false);
    
    if (isRunning) {
      setIsRunning(false);
      setActiveNode(null);
      addLog("手动中止执行");
      return;
    }

    setIsRunning(true);
    addLog("接收到新任务: '分析今天的科技新闻并发布推文'");
    
    let step = 0;
    const interval = setInterval(() => {
      step++;
      if (step === 1) {
        setActiveNode('llm');
        addLog("LLM 正在分析任务并拆解步骤...");
      } else if (step === 2) {
        setActiveNode('mem0');
        addLog("检索长期记忆，查找用户偏好的写作风格...");
      } else if (step === 3) {
        setActiveNode('browser');
        addLog("启动浏览器代理，搜索最新科技新闻...");
      } else if (step === 4) {
        setActiveNode('llm');
        addLog("正在生成最终推文内容...");
      } else if (step === 5) {
        setActiveNode('hub');
        addLog("任务执行完毕，结果已返回。");
        setIsRunning(false);
        setActiveNode(null);
        clearInterval(interval);
      }
    }, 2500);
  };

  const onConnect = useCallback((params: any) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  // 更新节点高亮状态
  useEffect(() => {
    setNodes(nds => 
      nds.map(node => ({
        ...node,
        style: { 
          ...node.style, 
          boxShadow: node.id === activeNode ? '0 0 15px rgba(249, 77, 58, 0.6)' : 'none',
          border: node.id === activeNode ? '1px solid #f94d3a' : '1px solid #2e2e33'
        }
      }))
    );
  }, [activeNode, setNodes]);

  return (
    <div className="h-full flex flex-col gap-4 pb-4">
      <Card className="bg-gradient-to-br from-dark-800 to-dark-900 border-dark-600 shadow-xl overflow-hidden shrink-0">
        <CardHeader className="pb-4 border-b border-dark-700/50 bg-dark-800/30">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-xl font-bold text-white flex items-center gap-2">
                <Workflow className="text-claw-400 h-6 w-6" />
                智能流监控 (Execution Flow)
              </CardTitle>
              <CardDescription className="mt-1 text-gray-400">
                实时可视化 AI 代理的决策与执行链路，洞察内部协作逻辑。当前: {useRealLogs ? 'Live Backend Logs' : 'Simulation Mode'}
              </CardDescription>
            </div>
            <button
              onClick={simulateExecution}
              className={clsx(
                "btn-primary flex items-center gap-2 transition-all",
                isRunning && !useRealLogs ? "bg-red-500 hover:bg-red-600" : "bg-claw-500 hover:bg-claw-600"
              )}
            >
              {isRunning && !useRealLogs ? <Square size={16} /> : <Play size={16} />}
              {isRunning && !useRealLogs ? '中止执行' : '运行测试任务'}
            </button>
          </div>
        </CardHeader>
      </Card>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* React Flow 区域 */}
        <Card className="flex-1 bg-dark-900 border-dark-600 shadow-xl overflow-hidden relative">
          {isRunning && (
            <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-dark-800/80 backdrop-blur border border-claw-500/50 px-3 py-1.5 rounded-full shadow-lg">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-claw-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-claw-500"></span>
              </span>
              <span className="text-xs font-medium text-claw-400 uppercase tracking-wider">Executing</span>
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            fitView
            className="bg-dark-900"
          >
            <Background color="#2e2e33" variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls className="bg-dark-800 border-dark-600 text-white fill-white" />
          </ReactFlow>
        </Card>

        {/* 日志监控区域 */}
        <Card className="w-80 bg-dark-800 border-dark-600 shadow-xl overflow-hidden flex flex-col shrink-0">
          <CardHeader className="py-3 px-4 border-b border-dark-700 bg-dark-900/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-gray-400" />
                <h3 className="text-sm font-semibold text-white">执行日志</h3>
              </div>
              {useRealLogs && (
                <div className="flex items-center gap-1.5 px-2 py-0.5 bg-green-500/10 border border-green-500/20 rounded text-xs text-green-400">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
                  </span>
                  Live
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-y-auto bg-dark-950 font-mono text-xs">
            <div ref={logsContainerRef} className="p-4 space-y-1.5 h-full overflow-y-auto">
              {logs.map((log, i) => (
                <div key={i} className={clsx(
                  "py-0.5 leading-relaxed break-words",
                  log.includes("新任务") ? "text-claw-400 font-bold" :
                  log.includes("完毕") ? "text-green-400" :
                  log.includes("中止") ? "text-red-400" :
                  log.includes("error") || log.includes("Error") ? "text-red-400" :
                  log.includes("warn") ? "text-yellow-400" :
                  "text-gray-400"
                )}>
                  {log}
                </div>
              ))}
              {logs.length === 0 && !isRunning && (
                <div className="flex items-center justify-center h-full text-gray-600">
                  等待执行指令...
                </div>
              )}
              {isRunning && (
                <div className="flex items-center gap-2 text-gray-500 pt-2">
                  <Loader2 size={12} className="animate-spin" />
                  <span>处理中...</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

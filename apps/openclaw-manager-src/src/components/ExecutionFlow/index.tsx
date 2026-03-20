import { useState, useCallback, useEffect } from 'react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, addEdge, BackgroundVariant, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Play, Square, Loader2, Workflow, Terminal } from 'lucide-react';
import clsx from 'clsx';

const initialNodes: Node[] = [
  { id: '1', position: { x: 250, y: 50 }, data: { label: '执行引擎核心 (Hub)' }, type: 'input', className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: '2', position: { x: 100, y: 150 }, data: { label: 'AI 决策集群 (LLM)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: '3', position: { x: 400, y: 150 }, data: { label: '浏览器代理 (Browser-Use)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: '4', position: { x: 250, y: 250 }, data: { label: '记忆检索器 (Mem0)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
];

const initialEdges = [
  { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: '#f94d3a' } },
  { id: 'e1-3', source: '1', target: '3', animated: true, style: { stroke: '#22d3ee' } },
  { id: 'e2-4', source: '2', target: '4', animated: true, style: { stroke: '#a78bfa' } },
];

export function ExecutionFlow() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [isRunning, setIsRunning] = useState(false);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([
    "[10:00:01] 引擎就绪，等待执行指令...",
  ]);

  const addLog = useCallback((msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`].slice(-50));
  }, []);

  const simulateExecution = () => {
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
        setActiveNode('2');
        addLog("LLM 正在分析任务并拆解步骤...");
      } else if (step === 2) {
        setActiveNode('4');
        addLog("检索长期记忆，查找用户偏好的写作风格...");
      } else if (step === 3) {
        setActiveNode('3');
        addLog("启动浏览器代理，搜索最新科技新闻...");
      } else if (step === 4) {
        setActiveNode('2');
        addLog("正在生成最终推文内容...");
      } else if (step === 5) {
        setActiveNode('1');
        addLog("任务执行完毕，结果已返回。");
        setIsRunning(false);
        setActiveNode(null);
        clearInterval(interval);
      }
    }, 2500);
  };

  const onConnect = useCallback((params: any) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

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
                实时可视化 AI 代理的决策与执行链路，洞察内部协作逻辑。
              </CardDescription>
            </div>
            <button
              onClick={simulateExecution}
              className={clsx(
                "btn-primary flex items-center gap-2 transition-all",
                isRunning ? "bg-red-500 hover:bg-red-600" : "bg-claw-500 hover:bg-claw-600"
              )}
            >
              {isRunning ? <Square size={16} /> : <Play size={16} />}
              {isRunning ? '中止执行' : '运行测试任务'}
            </button>
          </div>
        </CardHeader>
      </Card>

      <div className="flex-1 flex gap-4 min-h-0">
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

        <Card className="w-80 bg-dark-800 border-dark-600 shadow-xl overflow-hidden flex flex-col shrink-0">
          <CardHeader className="py-3 px-4 border-b border-dark-700 bg-dark-900/50">
            <div className="flex items-center gap-2">
              <Terminal size={14} className="text-gray-400" />
              <h3 className="text-sm font-semibold text-white">执行日志</h3>
            </div>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-y-auto bg-dark-950 font-mono text-xs">
            <div className="p-4 space-y-1.5">
              {logs.map((log, i) => (
                <div key={i} className={clsx(
                  "py-0.5 leading-relaxed break-words",
                  log.includes("新任务") ? "text-claw-400 font-bold" :
                  log.includes("完毕") ? "text-green-400" :
                  log.includes("中止") ? "text-red-400" :
                  "text-gray-400"
                )}>
                  {log}
                </div>
              ))}
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

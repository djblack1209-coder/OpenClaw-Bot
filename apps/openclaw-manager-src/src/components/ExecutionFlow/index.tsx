import { useState, useCallback, useEffect, useRef } from 'react';
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, addEdge, BackgroundVariant, Node, Edge, Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Play, Square, Loader2, Workflow, Terminal, Info } from 'lucide-react';
import { invoke } from '@tauri-apps/api/core';
import { isTauri } from '../../lib/tauri';
import clsx from 'clsx';
import dagre from 'dagre';

// 流程事件定义 — 与 Python 后端对齐
interface FlowEvent {
  source: string;
  target: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  msg: string;
  data: Record<string, unknown>;
  timestamp?: number;
}

// 初始默认布局
const initialNodes: Node[] = [
  { id: 'hub', position: { x: 250, y: 50 }, data: { label: '执行核心 (Hub)' }, type: 'input', className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'llm', position: { x: 100, y: 150 }, data: { label: 'AI 决策 (LLM)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'browser', position: { x: 400, y: 150 }, data: { label: '浏览器代理 (Browser-Use)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'mem0', position: { x: 250, y: 250 }, data: { label: '记忆检索器 (Mem0)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
  { id: 'trader', position: { x: 50, y: 250 }, data: { label: '量化交易 (Freqtrade)' }, className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg', style: {} },
];

const initialEdges: Edge[] = [
  { id: 'e-hub-llm', source: 'hub', target: 'llm', animated: true, style: { stroke: '#f94d3a' } },
  { id: 'e-hub-browser', source: 'hub', target: 'browser', animated: true, style: { stroke: '#22d3ee' } },
  { id: 'e-llm-mem0', source: 'llm', target: 'mem0', animated: true, style: { stroke: '#a78bfa' } },
  { id: 'e-llm-trader', source: 'llm', target: 'trader', animated: true, style: { stroke: '#4ade80' } },
];

// 自动排版引擎 (Dagre)
const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  
  
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 150, height: 50 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 75,
        y: nodeWithPosition.y - 25,
      },
    };
  });

  return { nodes: newNodes, edges };
};

export function ExecutionFlow() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [isRunning, setIsRunning] = useState(false);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [selectedNodeData, setSelectedNodeData] = useState<{ id: string, event: FlowEvent | null } | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const [useRealLogs, setUseRealLogs] = useState(true);
  const simulationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  // 用于追踪已经被添加过的动态节点，避免重复添加
  const seenNodes = useRef<Set<string>>(new Set(initialNodes.map(n => n.id)));

  // 自动滚动日志到底部
  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const addLog = useCallback((msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`].slice(-100));
  }, []);

  const handleFlowEvent = useCallback((eventStr: string) => {
    try {
      // 解析后端吐出的 JSON 结构
      const event: FlowEvent = JSON.parse(eventStr.replace('__CLAW_FLOW_EVENT__:', ''));
      event.timestamp = Date.now();
      
      setIsRunning(event.status === 'running' || event.status === 'pending');
      setActiveNode(event.target || event.source);
      
      // 更新日志流
      let logPrefix = "🔹";
      if (event.status === "running") logPrefix = "🔄";
      if (event.status === "success") logPrefix = "✅";
      if (event.status === "failed") logPrefix = "❌";
      
      addLog(`${logPrefix} [${event.source} -> ${event.target}] ${event.msg}`);

      // 动态构建或更新 ReactFlow 节点
      setNodes((nds) => {
        let updatedNodes = [...nds];
        let changed = false;

        // 如果出现了新节点，将其加入画布
        [event.source, event.target].forEach(nodeId => {
          if (nodeId && !seenNodes.current.has(nodeId)) {
            seenNodes.current.add(nodeId);
            changed = true;
            updatedNodes.push({
              id: nodeId,
              position: { x: 0, y: 0 }, // 先给个假坐标，后面会让 Dagre 自动排版
              data: { label: nodeId.toUpperCase(), lastEvent: null },
              className: 'bg-dark-800 text-white border-dark-500 rounded-lg shadow-lg',
            });
          }
        });

        // 更新节点发光状态与附带数据
        updatedNodes = updatedNodes.map(node => {
          const isActive = node.id === event.target || node.id === event.source;
          return {
            ...node,
            data: { 
               ...node.data, 
               lastEvent: isActive ? event : node.data.lastEvent 
            },
            style: {
              ...node.style,
              boxShadow: isActive ? '0 0 15px rgba(249, 77, 58, 0.6)' : 'none',
              border: isActive ? '1px solid #f94d3a' : '1px solid #2e2e33'
            }
          };
        });
        
        return changed ? getLayoutedElements(updatedNodes, edges).nodes : updatedNodes;
      });

      // 动态构建或更新连线 (Edges)
      if (event.source && event.target) {
        setEdges((eds) => {
          const edgeId = `e-${event.source}-${event.target}`;
          const existingEdgeIndex = eds.findIndex(e => e.id === edgeId);
          
          const newEdge = {
            id: edgeId,
            source: event.source,
            target: event.target,
            animated: event.status === 'running',
            style: { 
              stroke: event.status === 'failed' ? '#ef4444' : 
                      event.status === 'success' ? '#10b981' : '#f94d3a' 
            }
          };

          if (existingEdgeIndex >= 0) {
            const newEds = [...eds];
            newEds[existingEdgeIndex] = newEdge;
            return newEds;
          } else {
            const newEds = [...eds, newEdge];
            // 新增边后触发一次排版
            setTimeout(() => {
              setNodes(currNodes => getLayoutedElements(currNodes, newEds).nodes);
            }, 50);
            return newEds;
          }
        });
      }
      
      // 如果当前刚好选中了这个节点查看数据，实时更新抽屉里的数据
      setSelectedNodeData(prev => {
         if (prev && (prev.id === event.target || prev.id === event.source)) {
            return { id: prev.id, event };
         }
         return prev;
      });

    } catch (e) {
      console.error("流程事件解析失败", e);
    }
  }, [addLog, edges, setEdges, setNodes]);

  useEffect(() => {
    if (!isTauri() || !useRealLogs) return;
    
    // 从 clawbot 后端轮询实时日志
    const pollLogs = async () => {
      try {
        const newLogs = await invoke<string[]>('get_managed_service_logs', { label: 'ai.openclaw.agent', lines: 50 });
        if (newLogs && newLogs.length > 0) {
          // 只过滤出最后产生的真实事件并交由 handler 解析
          const events = newLogs.filter(line => line.includes('__CLAW_FLOW_EVENT__:'));
          if (events.length > 0) {
            // 这里为了平滑效果，只处理最后一条状态
            const latestEvent = events[events.length - 1];
            handleFlowEvent(latestEvent);
          } else {
            // 没有事件结构时，降级使用旧正则让节点发光
            const latestLog = newLogs[newLogs.length - 1];
            if (!latestLog.includes('__CLAW_FLOW_EVENT__')) {
              setLogs(newLogs.filter(l => !l.includes('__CLAW_FLOW_EVENT__')).slice(-100));
            }
          }
        }
      } catch (e) {
        console.error("[ExecutionFlow] Log polling failed:", e);
      }
    };
    
    pollLogs();
    const interval = setInterval(pollLogs, 1500); // 1.5秒刷新一次可观测性状态
    return () => clearInterval(interval);
  }, [useRealLogs, handleFlowEvent]);

  // 旧的正则兜底 (兼容没有埋点的旧爬虫/LLM代码)
  useEffect(() => {
    if (!activeNode) return;
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        style: { 
          ...node.style, 
          boxShadow: node.id === activeNode ? '0 0 15px rgba(249, 77, 58, 0.6)' : 'none',
          border: node.id === activeNode ? '1px solid #f94d3a' : '1px solid #2e2e33'
        }
      }))
    );
  }, [activeNode, setNodes]);

  const simulateExecution = () => {
    setUseRealLogs(false);
    
    if (isRunning) {
      setIsRunning(false);
      setActiveNode(null);
      if (simulationIntervalRef.current) {
        clearInterval(simulationIntervalRef.current);
        simulationIntervalRef.current = null;
      }
      addLog("手动中止执行");
      return;
    }

    setIsRunning(true);
    addLog("接收到新任务: '分析今天的科技新闻并发布推文'");
    
    let step = 0;
    const interval = setInterval(() => {
      step++;
      if (step === 1) {
        handleFlowEvent('__CLAW_FLOW_EVENT__:' + JSON.stringify({source: "hub", target: "llm", status: "running", msg: "分析任务拆解中", data: {prompt: "分析任务..."}}));
      } else if (step === 2) {
        handleFlowEvent('__CLAW_FLOW_EVENT__:' + JSON.stringify({source: "llm", target: "mem0", status: "running", msg: "检索风格记忆", data: {query: "风格", results: ["幽默", "短句"]}}));
      } else if (step === 3) {
        handleFlowEvent('__CLAW_FLOW_EVENT__:' + JSON.stringify({source: "llm", target: "browser", status: "running", msg: "启动浏览器执行抓取", data: {url: "https://news.ycombinator.com"}}));
      } else if (step === 4) {
        handleFlowEvent('__CLAW_FLOW_EVENT__:' + JSON.stringify({source: "browser", target: "llm", status: "success", msg: "内容返回", data: {content_length: 4056}}));
      } else if (step === 5) {
        handleFlowEvent('__CLAW_FLOW_EVENT__:' + JSON.stringify({source: "llm", target: "hub", status: "success", msg: "推文生成完毕", data: {tweet: "AI时代，重构比手搓更重要！"}}));
        setIsRunning(false);
        setActiveNode(null);
        clearInterval(interval);
        simulationIntervalRef.current = null;
      }
    }, 2500);
    simulationIntervalRef.current = interval;
  };

  // 组件卸载时清理轮询定时器
  useEffect(() => {
    return () => {
      if (simulationIntervalRef.current) {
        clearInterval(simulationIntervalRef.current);
      }
    };
  }, []);

  const onConnect = useCallback((params: Connection) => setEdges((eds) => addEdge(params, eds)), [setEdges]);
  
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
     if (node.data && node.data.lastEvent) {
         setSelectedNodeData({ id: node.id, event: node.data.lastEvent as FlowEvent });
     } else {
         setSelectedNodeData({ id: node.id, event: null });
     }
  }, []);

  return (
    <div className="h-full flex flex-col gap-4 pb-4">
      <Card className="bg-gradient-to-br from-dark-800 to-dark-900 border-dark-600 shadow-xl overflow-hidden shrink-0">
        <CardHeader className="pb-4 border-b border-dark-700/50 bg-dark-800/30">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-xl font-bold text-white flex items-center gap-2">
                <Workflow className="text-claw-400 h-6 w-6" />
                全景智能监控流 (Proactive Observability)
              </CardTitle>
              <CardDescription className="mt-1 text-gray-400">
                实时可视化 AI Agent 的思维链(CoT)、API调用及工具执行数据。当前模式: {useRealLogs ? 'Live Socket' : 'Simulation'}
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
              {isRunning && !useRealLogs ? '中止测试' : '运行打点测试'}
            </button>
          </div>
        </CardHeader>
      </Card>

      <div className="flex-1 flex gap-4 min-h-0 relative">
        {/* React Flow 区域 */}
        <Card className="flex-1 bg-dark-900 border-dark-600 shadow-xl overflow-hidden relative">
          {isRunning && (
            <div className="absolute top-4 left-4 z-10 flex items-center gap-2 bg-dark-800/80 backdrop-blur border border-claw-500/50 px-3 py-1.5 rounded-full shadow-lg">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-claw-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-claw-500"></span>
              </span>
              <span className="text-xs font-medium text-claw-400 uppercase tracking-wider">追踪中</span>
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            fitView
            className="bg-dark-900"
          >
            <Background color="#2e2e33" variant={BackgroundVariant.Dots} gap={16} size={1} />
            <Controls className="bg-dark-800 border-dark-600 text-white fill-white" />
          </ReactFlow>
        </Card>
        
        {/* 侧边滑动数据抽屉 (Data Drawer) - 取代死板的纯日志框 */}
        <div className={clsx(
            "w-96 flex flex-col gap-4 transition-all duration-300 transform",
            selectedNodeData ? "translate-x-0 opacity-100" : "translate-x-full opacity-0 absolute -right-full"
        )}>
            {selectedNodeData && (
              <Card className="flex-1 bg-dark-800 border-dark-500 shadow-2xl overflow-hidden flex flex-col relative">
                <button 
                  onClick={() => setSelectedNodeData(null)}
                  className="absolute top-3 right-3 text-gray-400 hover:text-white z-10"
                >
                  <Square size={16} />
                </button>
                <CardHeader className="py-3 px-4 border-b border-dark-700 bg-dark-900/50">
                  <div className="flex items-center gap-2">
                    <Info size={16} className="text-claw-400" />
                    <h3 className="text-sm font-semibold text-white">[{selectedNodeData.id.toUpperCase()}] 节点状态</h3>
                  </div>
                </CardHeader>
                <CardContent className="p-4 flex-1 overflow-y-auto font-mono text-xs bg-dark-950 text-gray-300">
                  {selectedNodeData.event ? (
                    <div className="space-y-4">
                        <div>
                            <span className="text-gray-500">消息: </span>
                            <span className="text-white">{selectedNodeData.event.msg}</span>
                        </div>
                        <div>
                            <span className="text-gray-500">状态: </span>
                            <span className={clsx(
                                "px-1.5 py-0.5 rounded",
                                selectedNodeData.event.status === 'running' ? 'bg-blue-500/20 text-blue-400' :
                                selectedNodeData.event.status === 'success' ? 'bg-green-500/20 text-green-400' :
                                'bg-red-500/20 text-red-400'
                            )}>{selectedNodeData.event.status.toUpperCase()}</span>
                        </div>
                        <div className="border-t border-dark-700 pt-2 mt-2">
                            <span className="text-gray-500 block mb-2">载荷数据:</span>
                            <pre className="bg-dark-900 p-2 rounded overflow-x-auto text-claw-200">
                                {JSON.stringify(selectedNodeData.event.data, null, 2)}
                            </pre>
                        </div>
                    </div>
                  ) : (
                    <div className="h-full flex items-center justify-center text-gray-600">
                        该节点暂无运行数据...
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
        </div>

        {/* 缩小版实时日志区 */}
        <Card className={clsx(
            "bg-dark-800 border-dark-600 shadow-xl overflow-hidden flex flex-col shrink-0 transition-all",
            selectedNodeData ? "w-80 absolute -right-full opacity-0" : "w-80"
        )}>
          <CardHeader className="py-3 px-4 border-b border-dark-700 bg-dark-900/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-gray-400" />
                <h3 className="text-sm font-semibold text-white">执行事件流</h3>
              </div>
              {useRealLogs && (
                <div className="flex items-center gap-1.5 px-2 py-0.5 bg-green-500/10 border border-green-500/20 rounded text-xs text-green-400">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
                  </span>
                  实时轮询
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-y-auto bg-dark-950 font-mono text-[11px]">
            <div ref={logsContainerRef} className="p-4 space-y-1.5 h-full overflow-y-auto">
              {logs.map((log, i) => (
                <div key={i} className={clsx(
                  "py-0.5 leading-relaxed break-words",
                  log.includes("🔄") ? "text-blue-400" :
                  log.includes("✅") ? "text-green-400" :
                  log.includes("❌") ? "text-red-400" :
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
                  <span>追踪数据拉取中...</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

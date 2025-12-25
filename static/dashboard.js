import React, { useState, useEffect } from 'react';
import { TrendingUp, AlertTriangle, CheckCircle, BarChart3, Zap } from 'lucide-react';

const AdvancedDashboard = () => {
    const [metrics, setMetrics] = useState({
        status: 'online',
        spread: { value: 0.008, percent: 2.8 },
        bid: 2.9,
        ask: 3.0,
        orderbook: {
            bids: [
                { price: 2.9, size: 4643 },
                { price: 2.9, size: 113206 },
                { price: 2.8, size: 18916 },
                { price: 2.7, size: 69462 },
                { price: 2.6, size: 86329 },
            ],
            asks: [
                { price: 3.0, size: 4734 },
                { price: 3.0, size: 110398 },
                { price: 3.1, size: 7401 },
                { price: 3.2, size: 27616 },
                { price: 3.3, size: 1922 },
            ],
        },
        logs: [
            '[17:19:50] ⚡ [Bitcoin Up or Down 0] Следующая проверка через 60 сек...',
            '[17:19:50] ✅ [Bitcoin Up or Down on November] SELL ордер #19100631 размещён',
            '[17:19:48] 📊 [Bitcoin Up or Down on November] Размещаю SELL @ 90.80¢',
            '[17:19:47] 🔄 [Bitcoin Up or Down on Nov] Переместил SELL: 98.90¢ → 90.80¢',
        ],
        systemHealth: {
            fillRate: 67.5,
            volatility: 0.34,
            imbalance: 0.12,
            inventorySkew: 0.45,
            spread_bps: 28,
            pnl: 12.45,
            ordersPlaced: 128,
            ordersF: 86,
        },
    });

    // Simulate real-time updates
    useEffect(() => {
        const interval = setInterval(() => {
            setMetrics(prev => ({
                ...prev,
                bid: prev.bid + (Math.random() - 0.5) * 0.01,
                ask: prev.ask + (Math.random() - 0.5) * 0.01,
                systemHealth: {
                    ...prev.systemHealth,
                    volatility: Math.max(0, Math.min(1, prev.systemHealth.volatility + (Math.random() - 0.5) * 0.05)),
                    fillRate: Math.max(0, Math.min(100, prev.systemHealth.fillRate + (Math.random() - 0.5) * 2)),
                    pnl: prev.systemHealth.pnl + (Math.random() - 0.5) * 0.5,
                },
            }));
        }, 2000);
        return () => clearInterval(interval);
    }, []);

    const getHealthColor = (value) => {
        if (value < 30) return 'text-red-500';
        if (value < 60) return 'text-yellow-500';
        return 'text-green-500';
    };

    const getVolatilityIndicator = (vol) => {
        if (vol < 0.2) return '🟢';
        if (vol < 0.5) return '🟡';
        return '🔴';
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-gray-100 p-4">
            {/* Header */}
            <div className="mb-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                        <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                            PolyMarket Pro Terminal
                        </h1>
                    </div>
                    <div className="text-sm text-gray-400">Status: LIVE</div>
                </div>
                <div className="text-sm text-gray-500">Bitcoin Up or Down on November 2024</div>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                {/* Spread Widget */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-2">SPREAD</div>
                    <div className="text-2xl font-bold text-yellow-400">⚠️ {metrics.spread.value.toFixed(3)}¢</div>
                    <div className="text-sm text-gray-500 mt-1">({metrics.spread.percent.toFixed(1)}%)</div>
                </div>

                {/* Bid/Ask */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-2">BID / ASK</div>
                    <div className="flex gap-2">
                        <div>
                            <div className="text-sm text-green-400">{metrics.bid.toFixed(2)}¢</div>
                            <div className="text-xs text-gray-500">BID</div>
                        </div>
                        <div className="border-l border-slate-600"></div>
                        <div>
                            <div className="text-sm text-red-400">{metrics.ask.toFixed(2)}¢</div>
                            <div className="text-xs text-gray-500">ASK</div>
                        </div>
                    </div>
                </div>

                {/* System Health */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-2">FILL RATE</div>
                    <div className={`text-2xl font-bold ${getHealthColor(metrics.systemHealth.fillRate)}`}>
                        {metrics.systemHealth.fillRate.toFixed(1)}%
                    </div>
                    <div className="w-full bg-slate-700 rounded h-1 mt-2">
                        <div
                            className={`h-1 rounded ${
                                metrics.systemHealth.fillRate > 70 ? 'bg-green-500' : 'bg-yellow-500'
                            }`}
                            style={{ width: `${Math.min(metrics.systemHealth.fillRate, 100)}%` }}
                        ></div>
                    </div>
                </div>

                {/* PnL */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-2">PROFIT/LOSS</div>
                    <div className={`text-2xl font-bold ${metrics.systemHealth.pnl > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${metrics.systemHealth.pnl.toFixed(2)}
                    </div>
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {/* Orderbook */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-3 font-semibold">📊 ORDERBOOK</div>

                    {/* Asks */}
                    <div className="mb-3">
                        <div className="text-xs text-gray-500 mb-1">ASKS (Sellers)</div>
                        {metrics.orderbook.asks.slice(0, 3).map((a, i) => (
                            <div key={i} className="flex justify-between text-xs mb-0.5">
                                <span className="text-red-400">{a.price.toFixed(1)}¢</span>
                                <span className="text-gray-500">{a.size.toLocaleString()}</span>
                            </div>
                        ))}
                    </div>

                    {/* Spread divider */}
                    <div className="border-t border-slate-600 my-2 py-1 text-center text-xs text-yellow-500">
                        SPREAD
                    </div>

                    {/* Bids */}
                    <div>
                        <div className="text-xs text-gray-500 mb-1">BIDS (Buyers)</div>
                        {metrics.orderbook.bids.slice(0, 3).map((b, i) => (
                            <div key={i} className="flex justify-between text-xs mb-0.5">
                                <span className="text-green-400">{b.price.toFixed(1)}¢</span>
                                <span className="text-gray-500">{b.size.toLocaleString()}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Advanced Metrics */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-3 font-semibold">⚙️ SYSTEM METRICS</div>

                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                            <span className="text-gray-400">Volatility</span>
                            <span className="text-gray-100">
                {getVolatilityIndicator(metrics.systemHealth.volatility)} {(metrics.systemHealth.volatility * 100).toFixed(1)}%
              </span>
                        </div>

                        <div className="flex justify-between">
                            <span className="text-gray-400">Imbalance</span>
                            <span className={metrics.systemHealth.imbalance > 0 ? 'text-red-400' : 'text-green-400'}>
                {metrics.systemHealth.imbalance > 0 ? '📈' : '📉'} {Math.abs(metrics.systemHealth.imbalance * 100).toFixed(1)}%
              </span>
                        </div>

                        <div className="flex justify-between">
                            <span className="text-gray-400">Inventory Skew</span>
                            <span className={Math.abs(metrics.systemHealth.inventorySkew) > 0.6 ? 'text-yellow-400' : 'text-gray-100'}>
                {(metrics.systemHealth.inventorySkew * 100).toFixed(0)}%
              </span>
                        </div>

                        <div className="flex justify-between">
                            <span className="text-gray-400">Dynamic Spread</span>
                            <span className="text-blue-400">{metrics.systemHealth.spread_bps} bps</span>
                        </div>

                        <div className="pt-2 border-t border-slate-600 flex justify-between">
                            <span className="text-gray-400">Orders Placed</span>
                            <span className="text-cyan-400">{metrics.systemHealth.ordersPlaced}</span>
                        </div>

                        <div className="flex justify-between">
                            <span className="text-gray-400">Orders Filled</span>
                            <span className="text-green-400">{metrics.systemHealth.ordersF}</span>
                        </div>
                    </div>
                </div>

                {/* Status Indicators */}
                <div className="col-span-1 bg-slate-800 border border-slate-700 rounded-lg p-4">
                    <div className="text-xs text-gray-400 mb-3 font-semibold">🔔 STATUS</div>

                    <div className="space-y-2">
                        <div className="flex items-center gap-2 text-xs">
                            <CheckCircle className="w-4 h-4 text-green-500" />
                            <span>Bot Running</span>
                        </div>

                        <div className="flex items-center gap-2 text-xs">
                            <Zap className="w-4 h-4 text-yellow-500" />
                            <span>High Activity</span>
                        </div>

                        <div className={`flex items-center gap-2 text-xs ${metrics.systemHealth.fillRate > 70 ? 'text-yellow-500' : 'text-green-500'}`}>
                            <TrendingUp className="w-4 h-4" />
                            <span>Fill Rate {metrics.systemHealth.fillRate > 70 ? 'High' : 'Normal'}</span>
                        </div>

                        <div className={`flex items-center gap-2 text-xs ${Math.abs(metrics.systemHealth.inventorySkew) > 0.6 ? 'text-red-500' : 'text-green-500'}`}>
                            <BarChart3 className="w-4 h-4" />
                            <span>Portfolio {Math.abs(metrics.systemHealth.inventorySkew) > 0.6 ? 'Skewed' : 'Balanced'}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Activity Logs */}
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                    <div className="text-xs text-gray-400 font-semibold">🗒 BOT ACTIVITY LOG</div>
                    <button className="text-xs text-gray-500 hover:text-gray-300 transition">Clear</button>
                </div>

                <div className="font-mono text-xs bg-black rounded p-3 h-32 overflow-y-auto space-y-1">
                    {metrics.logs.map((log, i) => (
                        <div key={i} className="text-gray-400 hover:text-gray-300">
                            <span className="text-blue-400">{log.substring(0, 9)}</span>
                            {log.substring(9)}
                        </div>
                    ))}
                </div>
            </div>

            {/* Footer Info */}
            <div className="mt-4 text-xs text-gray-600 text-center">
                Polymarket Market Maker Bot v2.0 • Advanced Pricing Engine • Real-time Metrics
            </div>
        </div>
    );
};

export default AdvancedDashboard;
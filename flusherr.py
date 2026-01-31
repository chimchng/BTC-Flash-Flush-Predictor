import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Literal

@dataclass
class MarketState:
    price: float
    funding_rate: float  # 0.00060 format
    funding_countdown_hours: float
    volume_24h: float
    rsi_1h: float
    support_level: float  # 81118
    resistance_level: float  # 83400
    structure: Literal['breakdown', 'consolidation', 'breakout']
    
class BTCFlushPredictor:
    def __init__(self):
        self.flush_probability = 0.0
        self.features = {}
        
    def calculate_funding_pressure(self, state: MarketState) -> float:
        """
        Funding pressure score: 0-1 (higher = more pressure on longs)
        """
        # Normalize funding (0.06% is extreme, 0.01% is normal)
        funding_z = min(abs(state.funding_rate) / 0.0008, 1.0)
        
        # Time decay factor (closer to funding = more urgency)
        # 3 hours left = 0.75 pressure, 0.5 hours left = 0.95 pressure
        time_pressure = 1 - (state.funding_countdown_hours / 8)
        time_pressure = max(0.3, min(time_pressure, 0.95))
        
        # If price is flat/down with positive funding = extreme pain
        price_vs_resistance = (state.resistance_level - state.price) / state.resistance_level
        
        if state.funding_rate > 0 and price_vs_resistance > 0.01:  # >1% below resistance
            funding_penalty = 1.5  # Longs trapped, paying premium to hold bags
        else:
            funding_penalty = 1.0
            
        self.features['funding_pressure'] = funding_z * time_pressure * funding_penalty
        return self.features['funding_pressure']
    
    def structural_breakdown_score(self, state: MarketState) -> float:
        """
        Measures how "broken" the structure is (0-1)
        """
        # Distance below key support
        if state.price < state.support_level:
            breakdown_severity = 1.0  # Already broken
        else:
            # How close to the cliff? (82300 vs 81118 = 1.4% away)
            distance_to_support = (state.price - state.support_level) / state.support_level
            breakdown_severity = max(0, 1 - (distance_to_support * 10))  # 10x multiplier for sensitivity
            
        # Volume confirmation (high volume on down move = institutional selling)
        volume_score = min(state.volume_24h / 5e9, 1.0)  # Normalize to 5B scale
        
        # RSI context (low RSI = oversold but can stay oversold in trend)
        rsi_score = (50 - state.rsi_1h) / 50 if state.rsi_1h < 50 else 0
        
        self.features['structure_score'] = (breakdown_severity * 0.5 + 
                                           volume_score * 0.3 + 
                                           rsi_score * 0.2)
        return self.features['structure_score']
    
    def time_regime_classifier(self, state: MarketState) -> str:
        """
        Classifies the specific time window (what we've been tracking)
        """
        hour_utc = datetime.utcnow().hour
        
        # Post-expiry consolidation (our current window: 08:00-16:00 UTC)
        if 8 <= hour_utc < 16:
            if state.funding_countdown_hours < 1:
                return "funding_liquidation_window"  # High volatility, forced closes
            else:
                return "consolidation_bleed"  # Slow funding drain
                
        # Asia open (high variance)
        elif 0 <= hour_utc < 8:
            return "asia_deleveraging"
            
        # US power hour
        elif 19 <= hour_utc <= 21:
            return "us_momentum"
            
        return "standard"
    
    def predict(self, state: MarketState) -> dict:
        """
        Main prediction engine
        """
        # Calculate components
        funding_pain = self.calculate_funding_pressure(state)
        structural_damage = self.structural_breakdown_score(state)
        regime = self.time_regime_classifier(state)
        
        # The "Flush" Model (specific to our current scenario)
        if regime == "funding_liquidation_window" and funding_pain > 0.6:
            # High probability of post-funding dump
            self.flush_probability = min(funding_pain * structural_damage * 1.2, 0.85)
            target = state.support_level * 0.995  # 81118 -> 80700 (your $80.7k)
            
        elif structural_damage > 0.7 and state.funding_rate > 0:
            # Structure broken, longs paying = slow bleed to support
            self.flush_probability = structural_damage * 0.8
            target = state.support_level
            
        elif regime == "consolidation_bleed" and state.rsi_1h < 40:
            # Boring chop lower (what we're seeing now)
            self.flush_probability = 0.5
            target = state.support_level
            
        else:
            self.flush_probability = 0.2
            target = state.resistance_level  # Reclaim scenario
            
        return {
            'flush_probability': self.flush_probability,
            'target_price': target,
            'regime': regime,
            'signal': 'SHORT_FLUSH' if self.flush_probability > 0.65 else 'NEUTRAL/CONSOLIDATION',
            'features': self.features,
            'confidence': 'HIGH' if self.flush_probability > 0.7 else 'MEDIUM' if self.flush_probability > 0.5 else 'LOW'
        }

# Real-time execution (how we'd use it right now)
if __name__ == "__main__":
    # Your current state at 10:00 local (13:00 UTC)
    current_state = MarketState(
        price=82845,
        funding_rate=0.00060,
        funding_countdown_hours=2.95,  # 2h57m
        volume_24h=3.71e9,
        rsi_1h=37.5,
        support_level=81118,
        resistance_level=83400,
        structure='consolidation'
    )
    
    model = BTCFlushPredictor()
    prediction = model.predict(current_state)
    
    print(f"""
    FLUSH PREDICTOR v1.0
    ====================
    Current Price: ${current_state.price:,}
    Funding Pressure: {prediction['features']['funding_pressure']:.2f}/1.0
    Structure Damage: {prediction['features']['structure_score']:.2f}/1.0
    Time Regime: {prediction['regime']}
    
    FLUSH PROBABILITY: {prediction['flush_probability']*100:.1f}%
    Target if Flush: ${prediction['target_price']:,.0f}
    Signal: {prediction['signal']}
    Confidence: {prediction['confidence']}
    
    EXECUTION LOGIC:
    - If price < {current_state.support_level} in next 3h → CASCADE MODE
    - If price > 83150 before funding → INVALIDATE
    - If still {current_state.price} at funding payout → POST-FUNDING DROP LIKELY
    """)
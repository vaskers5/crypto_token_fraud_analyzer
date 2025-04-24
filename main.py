import logging
from src.bot import ScamAnalyzerBot

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    bot = ScamAnalyzerBot()
    bot.run()
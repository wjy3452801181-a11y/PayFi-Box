require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const HASHKEY_RPC_URL = process.env.HASHKEY_RPC_URL || "https://testnet.hsk.xyz";
const HASHKEY_CHAIN_ID = Number(process.env.HASHKEY_CHAIN_ID || "133");
const DEPLOYER_PRIVATE_KEY = process.env.HASHKEY_OPERATOR_PRIVATE_KEY || process.env.DEPLOYER_PRIVATE_KEY || "";

module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      }
    }
  },
  networks: {
    hashkeyTestnet: {
      url: HASHKEY_RPC_URL,
      chainId: HASHKEY_CHAIN_ID,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : []
    }
  }
};

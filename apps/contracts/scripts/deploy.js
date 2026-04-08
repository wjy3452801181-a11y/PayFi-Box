const hre = require("hardhat");

function failFast(reason, hint) {
  console.error("Contract deployment configuration error.");
  console.error(`reason: ${reason}`);
  console.error(`hint: ${hint}`);
  process.exit(1);
}

function requireEnvConfig() {
  const privateKey =
    process.env.PRIVATE_KEY || process.env.HASHKEY_OPERATOR_PRIVATE_KEY || "";
  const rpcUrl = process.env.RPC_URL || process.env.HASHKEY_RPC_URL || "";

  if (!privateKey.trim()) {
    failFast(
      "missing private key",
      "set PRIVATE_KEY or HASHKEY_OPERATOR_PRIVATE_KEY in apps/contracts/.env"
    );
  }

  if (!rpcUrl.trim()) {
    failFast(
      "missing rpc url",
      "set RPC_URL or HASHKEY_RPC_URL in apps/contracts/.env"
    );
  }
}

async function main() {
  requireEnvConfig();

  const [deployer] = await hre.ethers.getSigners();
  if (!deployer) {
    failFast(
      "missing private key",
      "set PRIVATE_KEY or HASHKEY_OPERATOR_PRIVATE_KEY in apps/contracts/.env"
    );
  }
  const network = await hre.ethers.provider.getNetwork();

  console.log("Deploying PaymentExecutor...");
  console.log("Deployer:", deployer.address);
  console.log("Network chainId:", network.chainId.toString());

  const Factory = await hre.ethers.getContractFactory("PaymentExecutor");
  const contract = await Factory.deploy();
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  const tx = contract.deploymentTransaction();
  const operator = await contract.operator();

  console.log("PaymentExecutor deployed:", address);
  console.log("PaymentExecutor operator:", operator);
  if (tx && tx.hash) {
    const explorerBase = process.env.HASHKEY_EXPLORER_BASE || "https://testnet-explorer.hsk.xyz";
    console.log("Deployment tx hash:", tx.hash);
    console.log("Deployment tx explorer:", `${explorerBase.replace(/\/$/, "")}/tx/${tx.hash}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

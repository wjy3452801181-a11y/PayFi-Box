const hre = require("hardhat");

function failFast(reason, hint) {
  console.error("Demo token deployment configuration error.");
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
  const decimals = Number(process.env.HASHKEY_PAYMENT_TOKEN_DECIMALS || "6");
  const initialSupplyHuman = process.env.HASHKEY_DEMO_TOKEN_INITIAL_SUPPLY || "1000000";
  const initialSupply = hre.ethers.parseUnits(initialSupplyHuman, decimals);

  console.log("Deploying DemoToken...");
  console.log("Deployer:", deployer.address);
  console.log("Network chainId:", network.chainId.toString());
  console.log("Initial supply:", initialSupplyHuman);
  console.log("Decimals:", decimals);

  const Factory = await hre.ethers.getContractFactory("DemoToken");
  const token = await Factory.deploy("PayFi Demo USD", "pUSDT", decimals, initialSupply);
  await token.waitForDeployment();
  const address = await token.getAddress();
  const tx = token.deploymentTransaction();

  console.log("DemoToken deployed:", address);
  if (tx && tx.hash) {
    const explorerBase =
      process.env.HASHKEY_EXPLORER_BASE || "https://testnet-explorer.hsk.xyz";
    console.log("Deployment tx hash:", tx.hash);
    console.log("Deployment tx explorer:", `${explorerBase.replace(/\/$/, "")}/tx/${tx.hash}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
